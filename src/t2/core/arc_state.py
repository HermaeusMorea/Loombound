"""Per-choice arc state tracking (M2 Haiku classifier).

Extracted from PrefetchCache so arc state logic is independent of waypoint prefetch.
The only coupling back to PrefetchCache is the `current_arc_id` property, which
trigger() reads as a snapshot when kicking off C1 generation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field

from src.shared import config as _cfg
from src.shared.llm_utils import (
    ts as _ts,
    md_log as _md_log,
    OPUS_INPUT_COST as _OPUS_INPUT_COST,
    OPUS_OUTPUT_COST as _OPUS_OUTPUT_COST,
    OPUS_CACHE_READ_COST as _OPUS_CACHE_READ_COST,
)
from .arc_index import (
    ArcEmbeddingIndex,
    EMBEDDING_ONLY_THRESHOLD as _EMBEDDING_ONLY_THRESHOLD,
    HIGH_MATCH_THRESHOLD as _HIGH_MATCH_THRESHOLD,
)
from .m2_decision_engine import M2DecisionEngine
from .types import EncounterSlot

log = logging.getLogger(__name__)


def _band(value: int | None, lo: int, hi: int) -> str:
    """Discretize a precise value into a five-level tendency band.

    Duplicated from collector.py so arc_state.py does not create a circular
    import. Keep in sync with [src/t2/core/collector.py:24-41].
    """
    if value is None:
        return "unknown"
    if hi <= lo:
        return "moderate"
    ratio = (value - lo) / (hi - lo)
    t1, t2, t3, t4 = _cfg.BAND_THRESHOLDS
    if ratio <= t1:
        return "very_low"
    elif ratio <= t2:
        return "low"
    elif ratio <= t3:
        return "moderate"
    elif ratio <= t4:
        return "high"
    return "very_high"


@dataclass
class RunStateSnapshot:
    """Compact snapshot used by `needs_reclassification` to detect change."""

    health_band: str = "moderate"
    money_band: str = "moderate"
    sanity_band: str = "moderate"
    active_marks: frozenset[str] = field(default_factory=frozenset)
    trauma_count: int = 0

    @classmethod
    def from_run(cls, run) -> "RunStateSnapshot":
        cs = run.core_state
        ms = run.meta_state
        max_h = cs.max_health or 100
        traumas = ms.metadata.get("traumas", []) if hasattr(ms, "metadata") else []
        return cls(
            health_band=_band(cs.health, 0, max_h),
            money_band=_band(cs.money, 0, _cfg.MONEY_MAX),
            sanity_band=_band(cs.sanity, 0, 100),
            active_marks=frozenset(getattr(ms, "active_marks", []) or []),
            trauma_count=len(traumas),
        )


def needs_reclassification(prev: RunStateSnapshot, curr: RunStateSnapshot) -> bool:
    """Return True if arc classification should be refreshed mid-waypoint.

    Triggers on any h/m/s band crossing, any change in active_marks, or any
    new trauma recorded. No change → skip the LLM call, reuse _current_arc_id.
    """
    if prev.health_band != curr.health_band:
        return True
    if prev.money_band != curr.money_band:
        return True
    if prev.sanity_band != curr.sanity_band:
        return True
    if prev.active_marks != curr.active_marks:
        return True
    if curr.trauma_count > prev.trauma_count:
        return True
    return False


class ArcStateTracker:
    """Fires async M2 arc-state classifier calls.

    update_arc_state() → background thread → classifies arc state only.
    consume_arb_effects() → blocks briefly so callers can still synchronise;
    returns (empty_dict, "") since M2 no longer produces effects or rule ids.
    current_arc_id property → latest classified T2 cache entry_id.
    """

    def __init__(
        self,
        m2_engine: M2DecisionEngine,
        arc_index: ArcEmbeddingIndex | None = None,
    ) -> None:
        self._engine = m2_engine
        self._current_arc_id: int = 0
        # Legacy slot-keyed events so callers of consume_arb_effects() still
        # block briefly and then proceed. No effects or rule_ids are ever
        # populated now; both return values are empty by construction.
        self._effects_events: dict[EncounterSlot, threading.Event] = {}
        self._arc_lock = threading.Lock()

        # Step 4b: cache-hit gate. When the embedder is available and the
        # arc_index has embeddings, we try a cheap cosine lookup before
        # firing the LLM.
        self._arc_index = arc_index
        # Step 4c: LOOMBOUND_M2_EMBEDDING_ONLY=1 makes the embedding
        # classification the sole path (no LLM ever fires). Useful once 4b
        # replay accuracy is validated.
        self._embedding_only = os.environ.get("LOOMBOUND_M2_EMBEDDING_ONLY", "") == "1"

        # Stats counters for observability (accessible to tests / scripts).
        self.call_counts: dict[str, int] = {
            "cache_hit": 0,
            "ambiguous_fired": 0,
            "anomaly_fired": 0,
            "disabled_fired": 0,
            "embedding_only": 0,
        }

    @property
    def current_arc_id(self) -> int:
        with self._arc_lock:
            return self._current_arc_id

    def update_arc_state(
        self,
        quasi: str,
        next_waypoint_id: str | None,
        next_arb_idx: int | None,
    ) -> None:
        """Classify arc state — tries the semantic cache first, then LLM."""
        effects_key: EncounterSlot | None = None
        if next_waypoint_id is not None and next_arb_idx is not None:
            effects_key = EncounterSlot(waypoint_id=next_waypoint_id, arb_idx=next_arb_idx)
            with self._arc_lock:
                event = threading.Event()
                self._effects_events[effects_key] = event

        # Step 4b / 4c: cache-hit gate. If the embedding similarity is high
        # enough (or Step 4c embedding-only is on), set _current_arc_id
        # directly without firing the LLM.
        if self._arc_index is not None and self._arc_index.is_enabled():
            match = self._arc_index.lookup(quasi)
            if match is not None:
                high = _EMBEDDING_ONLY_THRESHOLD if self._embedding_only else _HIGH_MATCH_THRESHOLD
                if self._embedding_only:
                    counter_key = "embedding_only"
                elif match.source == "cache_hit" or match.score >= high:
                    counter_key = "cache_hit"
                else:
                    counter_key = None
                if counter_key is not None:
                    _md_log([
                        f"## [{_ts()}] M2 EMBEDDING HIT — "
                        f"wp={next_waypoint_id} arb={next_arb_idx} "
                        f"entry_id={match.entry_id} score={match.score:.3f} "
                        f"bucket={counter_key}",
                    ])
                    with self._arc_lock:
                        self._current_arc_id = match.entry_id
                        self.call_counts[counter_key] += 1
                        log.info(
                            "ArcStateTracker: %s arc_id=%d score=%.3f (no LLM)",
                            counter_key, match.entry_id, match.score,
                        )
                        if effects_key:
                            ev = self._effects_events.get(effects_key)
                            if ev:
                                ev.set()
                    return
                # Below high threshold and not embedding-only → fall through to LLM.
                if match.source == "anomaly":
                    self.call_counts["anomaly_fired"] += 1
                else:
                    self.call_counts["ambiguous_fired"] += 1
        else:
            self.call_counts["disabled_fired"] += 1

        quasi_copy = quasi

        def _run() -> None:
            asyncio.run(self._run_arc_update(quasi_copy, next_waypoint_id, next_arb_idx, effects_key))

        t = threading.Thread(
            target=_run,
            name=f"m2-{next_waypoint_id}-{next_arb_idx}",
            daemon=True,
        )
        t.start()

    def consume_arb_effects(
        self,
        waypoint_id: str,
        arb_idx: int,
        timeout: float = 8.0,
    ) -> tuple[dict[str, dict], str]:
        """Synchronise with the in-flight M2 call for this slot.

        Retained for backward compatibility with existing callers. Always
        returns (empty_dict, "") — effects and rule_id are handled by the
        templater and symbolic rule_selector respectively. Still blocks
        briefly so that `current_arc_id` is populated before C1 consumes it.
        """
        effects_key = EncounterSlot(waypoint_id=waypoint_id, arb_idx=arb_idx)

        with self._arc_lock:
            event = self._effects_events.get(effects_key)

        if event is not None:
            event.wait(timeout=timeout)

        with self._arc_lock:
            self._effects_events.pop(effects_key, None)

        return {}, ""

    async def _run_arc_update(
        self,
        quasi: str,
        next_waypoint_id: str | None,
        next_arb_idx: int | None,
        effects_key: EncounterSlot | None,
    ) -> None:
        label = f"{next_waypoint_id}:{next_arb_idx}" if next_waypoint_id else "entry_id_only"
        _md_log([
            f"## [{_ts()}] M2 ARC UPDATE REQUEST — {label}",
            "```",
            quasi,
            "```",
        ])

        try:
            entry_id, usage = await self._engine.classify(
                quasi,
                next_waypoint_id=next_waypoint_id,
                next_arb_idx=next_arb_idx,
            )
        except Exception as exc:
            log.error("M2 arc update failed: %s", exc)
            if effects_key:
                with self._arc_lock:
                    event = self._effects_events.get(effects_key)
                    if event:
                        event.set()
            return

        _inp = usage.get("input", 0)
        _out = usage.get("output", 0)
        _cr  = usage.get("cache_read", 0)
        _cc  = usage.get("cache_created", 0)
        _cost  = _inp * _OPUS_INPUT_COST + _out * _OPUS_OUTPUT_COST + _cr * _OPUS_CACHE_READ_COST
        _saved = _cr * (_OPUS_INPUT_COST - _OPUS_CACHE_READ_COST)
        _md_log([
            f"## [{_ts()}] M2 ARC UPDATE RESPONSE — {label} entry_id={entry_id}",
            f"tokens — input: {_inp}  output: {_out}  cache_created: {_cc}  cache_read: {_cr}",
            f"cost: ${_cost:.4f}  cache_savings: ${_saved:.4f}",
        ])

        with self._arc_lock:
            if entry_id >= 0:
                self._current_arc_id = entry_id
                log.info("M2: arc_id updated → %d", entry_id)
            if effects_key:
                event = self._effects_events.get(effects_key)
                if event:
                    event.set()
