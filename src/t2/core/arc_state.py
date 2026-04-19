"""Per-choice arc state tracking (M2 Haiku classifier).

Extracted from PrefetchCache so arc state logic is independent of node prefetch.
The only coupling back to PrefetchCache is the `current_arc_id` property, which
trigger() reads as a snapshot when kicking off C1 generation.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from src.shared.llm_utils import (
    ts as _ts,
    md_log as _md_log,
    OPUS_INPUT_COST as _OPUS_INPUT_COST,
    OPUS_OUTPUT_COST as _OPUS_OUTPUT_COST,
    OPUS_CACHE_READ_COST as _OPUS_CACHE_READ_COST,
)
from .m2_classifier import M2Classifier
from .types import EncounterSlot

log = logging.getLogger(__name__)


class ArcStateTracker:
    """Fires async M2 classifier calls after each player choice.

    update_arc_state() → background thread → classifies arc state + assigns option effects.
    consume_arb_effects() → blocks briefly to read the result.
    current_arc_id property → latest classified T2 cache entry_id.
    """

    def __init__(self, m2_classifier: M2Classifier) -> None:
        self._m2_classifier = m2_classifier
        self._current_arc_id: int = 0
        self._pending_effects: dict[EncounterSlot, dict[str, dict]] = {}
        self._pending_rule_ids: dict[EncounterSlot, str] = {}
        self._effects_events: dict[EncounterSlot, threading.Event] = {}
        self._arc_lock = threading.Lock()

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
        """Fire-and-forget M2 call after each player choice."""
        effects_key: EncounterSlot | None = None
        if next_waypoint_id is not None and next_arb_idx is not None:
            effects_key = EncounterSlot(waypoint_id=next_waypoint_id, arb_idx=next_arb_idx)
            with self._arc_lock:
                event = threading.Event()
                self._effects_events[effects_key] = event

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
        """Wait for and consume M2-assigned effects and rule selection."""
        effects_key = EncounterSlot(waypoint_id=waypoint_id, arb_idx=arb_idx)

        with self._arc_lock:
            event = self._effects_events.get(effects_key)

        if event is not None:
            event.wait(timeout=timeout)

        with self._arc_lock:
            effects = self._pending_effects.pop(effects_key, {})
            rule_id = self._pending_rule_ids.pop(effects_key, "")
            self._effects_events.pop(effects_key, None)

        if not effects:
            log.debug("ArcStateTracker: no M2 effects for '%s' arb %d.", waypoint_id, arb_idx)
        else:
            log.info("ArcStateTracker: consumed M2 effects for '%s' arb %d (%d option(s)) rule=%r.",
                     waypoint_id, arb_idx, len(effects), rule_id)
        return effects, rule_id

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
            entry_id, rule_id, effects_map, usage = await self._m2_classifier.classify(
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
            f"## [{_ts()}] M2 ARC UPDATE RESPONSE — {label} entry_id={entry_id} rule={rule_id!r}",
            f"tokens — input: {_inp}  output: {_out}  cache_created: {_cc}  cache_read: {_cr}",
            f"cost: ${_cost:.4f}  cache_savings: ${_saved:.4f}",
            f"effects: {len(effects_map)} option(s)",
        ])

        with self._arc_lock:
            if entry_id >= 0:
                self._current_arc_id = entry_id
                log.info("M2: arc_id updated → %d", entry_id)
            if effects_key and effects_map:
                self._pending_effects[effects_key] = effects_map
            if effects_key and rule_id:
                self._pending_rule_ids[effects_key] = rule_id
            if effects_key:
                event = self._effects_events.get(effects_key)
                if event:
                    event.set()
