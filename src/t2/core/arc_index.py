"""Semantic index over the arc-state catalog (Step 4b).

Purpose: when the quasi game state is clearly similar to an entry the LLM has
classified before, skip the LLM call and use that entry directly. This turns
arc classification from "every fire → Haiku" into "embed + cosine lookup,
fall back to Haiku only on ambiguous / anomalous states".

Design:
- At construction time we embed each catalog entry's 4-dim description once.
- At query time we embed the incoming `quasi_state` string and compute cosine
  against every entry. The caller uses the returned score to decide:
    cosine ≥ HIGH_MATCH_THRESHOLD  → cache hit, skip LLM
    cosine < LOW_MATCH_THRESHOLD   → anomaly, must fire LLM
    otherwise                     → ambiguous, fire LLM for safety
- Pure CPU, no external service. When the embedder is unavailable the index
  reports `is_enabled() == False` and all lookups return a miss.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Sequence

from src.shared import embedder as _embedder

log = logging.getLogger(__name__)


# Thresholds calibrated for paraphrase-multilingual-MiniLM-L12-v2.
# NOTE: quasi_state (long Chinese prose) vs catalog entry (short English tag
# sentence) is a long-short pairing and cosine tends to run lower than
# tag-vs-tag comparisons. These numbers are a starting point — watch the
# `call_counts` stats on ArcStateTracker and tune based on real replay.
HIGH_MATCH_THRESHOLD = 0.55   # above this → trust embedding, skip LLM
LOW_MATCH_THRESHOLD = 0.20    # below this → genuine anomaly; still fire LLM

# Step 4c: when LOOMBOUND_M2_EMBEDDING_ONLY is set, we lower HIGH to this and
# effectively make the embedding the sole classifier (it always takes the
# best-matching entry no matter how weak the match).
EMBEDDING_ONLY_THRESHOLD = 0.30


@dataclass(frozen=True)
class ArcMatch:
    """Result of a cache lookup against the arc index."""

    entry_id: int
    score: float       # max cosine observed
    source: str        # "cache_hit" | "ambiguous" | "anomaly" | "disabled"


_ARC_TRAJECTORY_DESC = {
    "rising": (
        "The story arc is gaining momentum. The protagonist's agency, "
        "knowledge, or position is expanding. Discoveries accumulate. "
        "Obstacles appear but are overcome. Confidence is building."
    ),
    "plateau": (
        "Progress has levelled off. The protagonist holds a stable "
        "position but cannot easily advance or retreat. Tension persists "
        "without resolution — a period of waiting, negotiation, or "
        "consolidation."
    ),
    "climax": (
        "The decisive confrontation is here. Maximum pressure converges. "
        "Everything the run has built toward is arriving now. Resources "
        "are depleted or committed. There is no safe exit."
    ),
    "resolution": (
        "The major conflict has been decided. Aftermath and consequence "
        "are being processed. The protagonist integrates what happened "
        "and moves toward a new equilibrium — positive, negative, or "
        "ambiguous."
    ),
    "pivot": (
        "An unexpected reversal has redirected the run entirely. A "
        "betrayal, revelation, or sudden shift has invalidated previous "
        "assumptions. The protagonist must reorient from scratch."
    ),
}

_WORLD_PRESSURE_DESC = {
    "low": (
        "The environment is permissive. The protagonist can act without "
        "immediate threat. Exploration and preparation are viable. "
        "Mistakes are recoverable."
    ),
    "moderate": (
        "Some opposition or constraint is present. The protagonist must "
        "act deliberately. Some choices carry real risk. The situation "
        "has stakes but not yet urgency."
    ),
    "high": (
        "Active threat or crisis. The protagonist is under real pressure. "
        "Time or resources are limited. Errors carry significant cost. "
        "Tension is felt in every scene."
    ),
    "critical": (
        "Existential pressure. The protagonist is at the edge of failure, "
        "madness, or death. Every decision is high-stakes. The environment "
        "is actively hostile. Survival is not guaranteed."
    ),
}

_NARRATIVE_PACING_DESC = {
    "slow": (
        "Scenes breathe. Information is revealed gradually. Atmosphere "
        "and lore dominate over action. The player has time to absorb "
        "environment, character, and world."
    ),
    "steady": (
        "Measured forward movement. Events progress logically. No rush, "
        "but no stagnation. Standard adventure pacing."
    ),
    "accelerating": (
        "The pace is increasing. Each scene triggers the next more "
        "urgently. Downtime is shrinking. The run is building toward "
        "something the player can feel."
    ),
    "sprint": (
        "Maximum velocity. Back-to-back crises with no breathing room. "
        "Scenes are short and punchy. Every moment matters."
    ),
}

_PENDING_INTENT_DESC = {
    "exploration": (
        "Seeking new information, locations, or relationships. The next "
        "action is investigative or expansive — open-ended curiosity."
    ),
    "confrontation": (
        "A direct challenge, conflict, or negotiation with an opposing "
        "force. The protagonist is moving toward friction."
    ),
    "revelation": (
        "A key truth is about to surface — through discovery, confession, "
        "or forced disclosure. Answers are coming, wanted or not."
    ),
    "recovery": (
        "The protagonist is regrouping: healing, restoring resources, "
        "processing loss, or rebuilding after damage."
    ),
    "transition": (
        "A threshold crossing. Moving between acts, locations, or "
        "identities. The current chapter is ending; the next is unknown."
    ),
}


def _describe_entry(entry: dict) -> str:
    """Turn one catalog row into a rich natural-language description.

    Preference order:
      1. Authored `description` field (the curated narrative-stage prose that
         ships in data/arc_state_catalog.json). Optionally prefixed by `label`
         for extra keyword signal.
      2. Fallback: expand the 4 dimensions with the per-value desc tables
         below, then concatenate (used only for catalogs that have no
         `description` field, e.g. legacy or test entries).
    """
    authored = (entry.get("description") or "").strip()
    if authored:
        label = (entry.get("label") or "").strip()
        return f"{label}. {authored}" if label else authored

    arc = entry.get("arc_trajectory", "")
    pressure = entry.get("world_pressure", "")
    pacing = entry.get("narrative_pacing", "")
    intent = entry.get("pending_intent", "")
    parts = [
        _ARC_TRAJECTORY_DESC.get(arc, f"Arc trajectory: {arc}.") if arc else "",
        _WORLD_PRESSURE_DESC.get(pressure, f"World pressure: {pressure}.") if pressure else "",
        _NARRATIVE_PACING_DESC.get(pacing, f"Narrative pacing: {pacing}.") if pacing else "",
        _PENDING_INTENT_DESC.get(intent, f"Pending intent: {intent}.") if intent else "",
    ]
    return " ".join(p for p in parts if p)


class ArcEmbeddingIndex:
    """In-memory cosine index over the arc-state catalog."""

    def __init__(self, entries: Sequence[dict]) -> None:
        self._entries: list[dict] = list(entries)
        self._vectors: list[list[float]] = []
        self._enabled: bool = False

        if _embedder.is_available() and self._entries:
            descriptions = [_describe_entry(e) for e in self._entries]
            try:
                self._vectors = _embedder.embed_batch(descriptions)
                self._enabled = True
            except Exception as exc:
                log.warning("ArcEmbeddingIndex: embedding failed (%s) — disabled", exc)
                self._vectors = []
                self._enabled = False

    @classmethod
    def from_json(cls, raw_json: str) -> "ArcEmbeddingIndex":
        try:
            data = json.loads(raw_json) if raw_json else []
        except json.JSONDecodeError:
            data = []
        if isinstance(data, dict):
            data = data.get("entries") or []
        return cls(data if isinstance(data, list) else [])

    def is_enabled(self) -> bool:
        return self._enabled

    def lookup(
        self,
        quasi_state: str,
        *,
        high: float = HIGH_MATCH_THRESHOLD,
        low: float = LOW_MATCH_THRESHOLD,
    ) -> ArcMatch | None:
        """Classify `quasi_state` by cosine against the catalog.

        Returns None when the index is disabled (caller must then fire LLM).
        """
        if not self._enabled or not self._vectors:
            return None
        try:
            query = _embedder.embed(quasi_state)
        except Exception as exc:
            log.warning("ArcEmbeddingIndex: query embed failed (%s)", exc)
            return None

        best_idx = 0
        best_score = -1.0
        for idx, vec in enumerate(self._vectors):
            score = _embedder.cosine(query, vec)
            if score > best_score:
                best_idx = idx
                best_score = score

        entry = self._entries[best_idx]
        entry_id = int(entry.get("entry_id", best_idx))

        if best_score >= high:
            source = "cache_hit"
        elif best_score < low:
            source = "anomaly"
        else:
            source = "ambiguous"
        return ArcMatch(entry_id=entry_id, score=best_score, source=source)
