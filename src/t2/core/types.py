"""Data types for the LLM content generation pipeline.

Two-layer asset model:
  WaypointSeedPack      — Slow Core output (Claude): high-density structured plan
                      for one node, containing multiple EncounterSeed entries.
  ResolvedEncounter — Fast Core output (gemma4): full encounter JSON dict
                        ready for validate_arbitration_asset → runtime.

Prefetch layer:
  PrefetchEntry     — one node's prefetch state, held by PrefetchCache.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import uuid


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Seed layer — Slow Core output
# ---------------------------------------------------------------------------

@dataclass
class EncounterOptionSeed:
    """One option inside an EncounterSeed.

    Effects dict keys: health_delta, money_delta, sanity_delta (int),
    add_marks (list[str]), add_events (list[str] — filled by Fast Core).
    """
    option_id: str
    intent: str
    tags: list[str] = field(default_factory=list)
    effects: dict[str, Any] = field(default_factory=dict)


@dataclass
class EncounterSeed:
    """Quasi-level plan for one encounter inside a node.

    scene_concept and sanity_axis are the Slow Core's core contribution:
    they give Fast Core the narrative direction needed to write coherent text.
    """
    scene_type: str
    scene_concept: str        # e.g. "rain-soaked crossroads, three paths..."
    sanity_axis: str          # e.g. "safety vs occult risk when already strained"
    options: list[EncounterOptionSeed] = field(default_factory=list)
    tendency: dict[str, str] = field(default_factory=dict)


@dataclass
class WaypointSeedPack:
    """Slow Core output: structured plan for all encounters in one future node.

    One Slow Core API call produces one WaypointSeedPack.
    Fast Core expands each EncounterSeed into a full encounter JSON dict.
    """
    target_waypoint_id: str
    node_theme: str
    narrative_direction: str
    encounters: list[EncounterSeed] = field(default_factory=list)
    seed_id: str = field(default_factory=lambda: _new_id("seed"))
    created_at: datetime = field(default_factory=_now)
    # Token usage from the Slow Core API call that produced this pack.
    # Keys: input, output, cache_created, cache_read (all int).
    usage: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Resolved layer — Fast Core output
# ---------------------------------------------------------------------------

@dataclass
class ResolvedEncounter:
    """Fast Core output: one complete encounter JSON dict.

    payload passes validate_arbitration_asset and is consumed directly
    by the existing runtime pipeline (load_current_encounter / _play_encounter).
    """
    payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prefetch layer
# ---------------------------------------------------------------------------

PrefetchStatus = Literal["pending", "ready", "failed", "stale"]


@dataclass
class PrefetchEntry:
    """Prefetch state for one future waypoint, held in PrefetchCache."""
    waypoint_id: str
    status: PrefetchStatus = "pending"
    seed_pack: WaypointSeedPack | None = None
    # Resolved encounter payloads in order — consumed by _play_node.
    resolved: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    created_at: datetime = field(default_factory=_now)

    def mark_ready(self, seed: WaypointSeedPack, resolved: list[dict[str, Any]]) -> None:
        self.seed_pack = seed
        self.resolved = resolved
        self.status = "ready"

    def mark_failed(self, error: str) -> None:
        self.error = error
        self.status = "failed"

    def mark_stale(self) -> None:
        self.status = "stale"
