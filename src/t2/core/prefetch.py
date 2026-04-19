"""Prefetch cache — background generation of future node content.

Strategy (PRISM timing pattern adapted for Loombound):
  - When player enters Node N, trigger background generation of Node N+1 content.
  - Generation runs in a daemon thread while the player plays through Node N.
  - When _play_node loads Node N+1, it checks the cache first.
  - Cache hit  → use LLM-generated encounter payloads instead of authored JSON.
  - Cache miss → fall back to authored JSON as before (no regression).

Arc state tracking (per-choice Opus calls):
  - After each player choice, play_cli calls update_arc_state() which fires an
    async Opus M2 call in a background thread.
  - Opus returns entry_id (current arc state) + per-option effects for the next arb.
  - _current_arc_id is updated immediately when Opus responds.
  - Effects are stored keyed by "waypoint_id:arb_idx" and consumed by play_cli just
    before displaying the target encounter.
  - C1 prefetch reads _current_arc_id directly — no Opus call needed.

Thread model:
  play_cli is synchronous (blocking input). Background generation uses
  threading.Thread + asyncio.run() inside the thread, keeping the main loop
  unchanged. Thread is daemon so it does not block game exit.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import sys
import threading
import time
import traceback
from typing import Any

from src.t0.memory.models import CoreStateView
from src.t2.memory.a2_store import RuntimeTableStore
from src.t0.memory.types import RunMemory
from src.shared.llm_utils import (
    ts as _ts,
    md_log as _md_log,
    HAIKU_INPUT_COST as _HAIKU_INPUT_COST,
    HAIKU_OUTPUT_COST as _HAIKU_OUTPUT_COST,
)
from .arc_state import ArcStateTracker

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.t1.core import C1Expander, C1Config
from .m2_decision_engine import M2DecisionEngine
from .types import EncounterSeed, EncounterOptionSeed, WaypointSeedPack, PrefetchEntry

log = logging.getLogger(__name__)


def _arc_row_to_tendency(arc_row: Any) -> dict[str, str]:
    """Convert a T2 cache entry into a Fast Core tendency payload."""

    return {
        "entry_id": str(getattr(arc_row, "entry_id", "")),
        "arc_trajectory": getattr(arc_row, "arc_trajectory", ""),
        "world_pressure": getattr(arc_row, "world_pressure", ""),
        "narrative_pacing": getattr(arc_row, "narrative_pacing", ""),
        "pending_intent": getattr(arc_row, "pending_intent", ""),
    }


def _merge_preloaded_seed(
    skeleton: Any,
    arc_row: Any,
) -> EncounterSeed:
    """Blend a T1 cache node skeleton with the runtime T2 cache tendency.

    Effects in the seed come from the T1 cache (Haiku-generated placeholders).
    Haiku per-option effects are applied separately at play time via play_cli's
    _overlay_effects, which patches the expanded payload dict directly.
    """
    raw_options = skeleton.options or []
    arb_options = [
        EncounterOptionSeed(
            option_id=o.get("option_id", f"opt_{i}"),
            intent=o.get("intent", ""),
            tags=o.get("tags", []),
            effects=o.get("effects", {}),
        )
        for i, o in enumerate(raw_options)
    ]

    tendency = _arc_row_to_tendency(arc_row)
    tendency_text = (
        f"arc_trajectory={tendency['arc_trajectory']}, "
        f"world_pressure={tendency['world_pressure']}, "
        f"narrative_pacing={tendency['narrative_pacing']}, "
        f"pending_intent={tendency['pending_intent']}"
    )

    return EncounterSeed(
        scene_type=skeleton.scene_type,
        scene_concept=(
            f"{skeleton.scene_concept}\n"
            f"Runtime arc tendency to honor: {tendency_text}."
        ),
        sanity_axis=(
            f"{skeleton.sanity_axis}\n"
            f"Current dramatic emphasis: {tendency['world_pressure']} pressure, "
            f"{tendency['narrative_pacing']} pacing, {tendency['pending_intent']} intent."
        ),
        options=arb_options,
        tendency=tendency,
    )


# ---------------------------------------------------------------------------
# PrefetchCache
# ---------------------------------------------------------------------------

class PrefetchCache:
    """Manages background generation and arc-state tracking for the active run.

    Two independent subsystems:

    1. Node content prefetch (C1):
       trigger() → background thread generates encounter payloads for a future node.
       consume() → returns payloads (or None on cache miss/failure).

    2. Per-choice arc updates (Opus M2):
       update_arc_state() → after each player choice, fires async Opus call.
       consume_arb_effects() → blocks briefly for Opus result, returns option effects.
       _current_arc_id property → latest classified T2 cache entry_id.
    """

    def __init__(
        self,
        fast_cfg: "C1Config | None" = None,
        lang: str = "en",
        m2_engine: M2DecisionEngine | None = None,
    ) -> None:
        from src.t1.core import C1Expander, C1Config
        fast_cfg = fast_cfg or C1Config()
        fast_cfg.lang = lang
        self._fast = C1Expander(fast_cfg)
        self._arc = ArcStateTracker(m2_engine) if m2_classifier else None

        # Node content cache
        self._cache: dict[str, PrefetchEntry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface — node content prefetch
    # ------------------------------------------------------------------

    def warmup(self) -> None:
        """Warm up the local model in a background thread."""
        def _run() -> None:
            asyncio.run(self._fast.warmup())

        t = threading.Thread(target=_run, name="fastcore-warmup", daemon=True)
        t.start()

    def trigger(
        self,
        target_waypoint_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        encounter_count: int,
    ) -> None:
        """Start background generation for target_waypoint_id if not already running.

        Uses the preloaded path: T1 cache skeleton + current _current_arc_id tendency
        → C1 expansion. If T1 cache is unavailable, marks the entry as failed
        and the caller falls back to authored JSON.
        """
        with self._lock:
            existing = self._cache.get(target_waypoint_id)
            if existing and existing.status in ("pending", "ready"):
                log.debug("Prefetch: '%s' already %s, skipping trigger.",
                          target_waypoint_id, existing.status)
                return
            entry = PrefetchEntry(waypoint_id=target_waypoint_id, status="pending")
            self._cache[target_waypoint_id] = entry

        log.info("Prefetch: triggering background generation for '%s' (%d encounter(s)).",
                 target_waypoint_id, encounter_count)

        # Snapshot the arc_id at trigger time — C1 uses this for tendency
        arc_id_snapshot = self._arc.current_arc_id if self._arc else 0

        # Deep-copy state so background thread doesn't race with main loop
        state_snapshot = copy.deepcopy(core_state)
        memory_snapshot = copy.deepcopy(run_memory)

        def _run() -> None:
            asyncio.run(
                self._generate(
                    target_waypoint_id,
                    state_snapshot,
                    memory_snapshot,
                    encounter_count,
                    arc_id_snapshot,
                )
            )

        t = threading.Thread(
            target=_run,
            name=f"prefetch-{target_waypoint_id}",
            daemon=True,
        )
        t.start()

    def wait_for(self, waypoint_id: str, timeout: float = 120.0) -> None:
        """Block until prefetch for waypoint_id is no longer pending."""
        with self._lock:
            entry = self._cache.get(waypoint_id)
        if entry is None or entry.status != "pending":
            return

        deadline = time.monotonic() + timeout
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        print(f"\033[2m", end="", file=sys.stderr)
        try:
            while time.monotonic() < deadline:
                with self._lock:
                    entry = self._cache.get(waypoint_id)
                if entry is None or entry.status != "pending":
                    break
                print(f"\r{spinner[idx % len(spinner)]} generating content...",
                      end="", file=sys.stderr, flush=True)
                idx += 1
                time.sleep(0.3)
        finally:
            print(f"\r\033[0m\033[K", end="", file=sys.stderr, flush=True)

    def consume(self, waypoint_id: str) -> list[dict[str, Any]] | None:
        """Return resolved encounter payloads if generation succeeded."""
        with self._lock:
            entry = self._cache.get(waypoint_id)
            if entry is None:
                log.debug("Prefetch: no entry for '%s' — authored fallback.", waypoint_id)
                return None

            status = entry.status
            error = entry.error
            if status == "ready":
                resolved = list(entry.resolved)
                arb_count = len(resolved)
                del self._cache[waypoint_id]
            else:
                resolved = None
                arb_count = 0

        if status == "pending":
            log.info("Prefetch: '%s' still generating — authored fallback.", waypoint_id)
            return None
        if status == "failed":
            log.warning("Prefetch: '%s' generation failed (%s) — authored fallback.",
                        waypoint_id, error)
            return None
        if status == "stale":
            log.info("Prefetch: '%s' is stale — authored fallback.", waypoint_id)
            return None

        log.info("Prefetch: '%s' ready — using %d LLM-generated encounter(s).",
                 waypoint_id, arb_count)
        return resolved

    def get_error(self, waypoint_id: str) -> str | None:
        """Return the error message if the last generation attempt for this waypoint failed."""
        with self._lock:
            entry = self._cache.get(waypoint_id)
            if entry and entry.status == "failed":
                return entry.error
        return None

    def invalidate(self, waypoint_id: str) -> None:
        """Mark a cached entry as stale (e.g. after a major state change)."""
        with self._lock:
            entry = self._cache.get(waypoint_id)
            if entry:
                entry.mark_stale()

    # ------------------------------------------------------------------
    # Public interface — per-choice arc state updates (delegates to ArcStateTracker)
    # ------------------------------------------------------------------

    def update_arc_state(
        self,
        quasi: str,
        next_waypoint_id: str | None,
        next_arb_idx: int | None,
    ) -> None:
        if self._arc:
            self._arc.update_arc_state(quasi, next_waypoint_id, next_arb_idx)

    def consume_arb_effects(
        self,
        waypoint_id: str,
        arb_idx: int,
        timeout: float = 8.0,
    ) -> tuple[dict[str, dict], str]:
        if self._arc:
            return self._arc.consume_arb_effects(waypoint_id, arb_idx, timeout)
        return {}, ""

    # ------------------------------------------------------------------
    # Internal async generation pipeline — preloaded path
    # ------------------------------------------------------------------

    async def _generate(
        self,
        target_waypoint_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        encounter_count: int,
        arc_id_snapshot: int,
    ) -> None:
        try:
            if not run_memory.tables.has_caches():
                reason = "arc_state_catalog/scene_skeletons not loaded"
                log.warning("Prefetch: '%s' skipped — %s.", target_waypoint_id, reason)
                with self._lock:
                    entry = self._cache.get(target_waypoint_id)
                    if entry:
                        entry.mark_failed(reason)
                return
            await self._generate_preloaded(
                target_waypoint_id,
                core_state,
                run_memory,
                encounter_count,
                arc_id_snapshot,
            )
        except Exception as exc:
            tb = traceback.format_exc()
            _md_log([
                f"## [{_ts()}] FAILED — `{target_waypoint_id}`",
                f"error: {exc}",
                "```",
                tb,
                "```",
            ])
            log.error("Prefetch: '%s' generation failed: %s", target_waypoint_id, exc, exc_info=True)
            with self._lock:
                entry = self._cache.get(target_waypoint_id)
                if entry:
                    entry.mark_failed(str(exc))

    async def _generate_preloaded(
        self,
        target_waypoint_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        encounter_count: int,
        arc_id_snapshot: int,
    ) -> None:
        """Preloaded path: look up T2 cache + T1 cache, expand with Fast Core.

        No Haiku call here — arc tendency comes from arc_id_snapshot which was
        captured at trigger() time from _current_arc_id.
        """
        # Step 1: arc-state catalog lookup for arc tendency
        arc_row = run_memory.tables.lookup_arc(arc_id_snapshot)
        if arc_row is None:
            # Fallback to entry 0 if snapshot id is missing
            arc_row = run_memory.tables.lookup_arc(0)
        if arc_row is None:
            reason = f"arc_state_catalog missing entry_id={arc_id_snapshot} and no entry 0"
            log.warning("Prefetch[preloaded]: '%s' — %s.", target_waypoint_id, reason)
            with self._lock:
                entry = self._cache.get(target_waypoint_id)
                if entry:
                    entry.mark_failed(reason)
            return

        # Step 2: scene skeletons lookup
        node_entry = run_memory.tables.lookup_waypoint(target_waypoint_id)
        if node_entry is None or not node_entry.encounters:
            reason = f"scene_skeletons missing waypoint_id={target_waypoint_id}"
            log.warning("Prefetch[preloaded]: '%s' — %s.", target_waypoint_id, reason)
            with self._lock:
                entry = self._cache.get(target_waypoint_id)
                if entry:
                    entry.mark_failed(reason)
            return

        _md_log([
            f"## [{_ts()}] SCENE SKELETON LOOKUP — waypoint `{target_waypoint_id}` (arc_id={arc_id_snapshot})",
            f"waypoint_type: {node_entry.waypoint_type}",
            f"label: {node_entry.label}",
            f"encounters: {len(node_entry.encounters)}",
            f"arc_trajectory: {arc_row.arc_trajectory}",
            f"world_pressure: {arc_row.world_pressure}",
        ])

        # Step 3: Merge T1 cache skeletons with arc tendency
        merged_seeds: list[EncounterSeed] = []
        for idx in range(encounter_count):
            skeleton = node_entry.encounters[min(idx, len(node_entry.encounters) - 1)]
            arb_seed = _merge_preloaded_seed(skeleton, arc_row)
            merged_seeds.append(arb_seed)
            arb_id = f"{target_waypoint_id}_t1_{idx:02d}"
            _md_log([
                f"## [{_ts()}] C1 REQUEST (preloaded) — `{arb_id}`",
                f"scene_concept: {arb_seed.scene_concept}",
                f"sanity_axis: {arb_seed.sanity_axis}",
                f"tendency: {arb_seed.tendency}",
            ])

        # Step 4: Fast Core expands each encounter
        resolved = await self._expand_encounters(merged_seeds, target_waypoint_id, "t1", core_state)

        # Step 5: Assemble seed_pack and store in cache
        seed_pack = WaypointSeedPack(
            target_waypoint_id=target_waypoint_id,
            node_theme=arc_row.arc_trajectory,
            narrative_direction=arc_row.pending_intent,
            encounters=merged_seeds,
        )

        with self._lock:
            entry = self._cache.get(target_waypoint_id)
            if entry:
                entry.mark_ready(seed_pack, resolved)

        _md_log([
            f"## [{_ts()}] COMPLETE (preloaded) — `{target_waypoint_id}` "
            f"({len(resolved)} encounter(s), arc_id={arc_id_snapshot})",
        ])
        log.info(
            "Prefetch[preloaded]: '%s' complete (%d arb(s), arc_id=%d).",
            target_waypoint_id, len(resolved), arc_id_snapshot,
        )

    async def _expand_encounters(
        self,
        seeds: list[EncounterSeed],
        waypoint_id: str,
        id_prefix: str,
        core_state: CoreStateView,
    ) -> list[dict[str, Any]]:
        """Expand a list of EncounterSeeds via Fast Core; log each call."""
        resolved: list[dict[str, Any]] = []
        for idx, arb_seed in enumerate(seeds):
            arb_id = f"{waypoint_id}_{id_prefix}_{idx:02d}"
            payload, fc_usage = await self._fast.expand(arb_seed, core_state, arb_id)
            resolved.append(payload)

            ctx = payload.get("context", {})
            meta = ctx.get("metadata", {})
            _md_log([
                f"## [{_ts()}] C1 RESPONSE ({id_prefix}) — `{arb_id}`",
                f"tokens — prompt: {fc_usage.get('prompt_tokens', '?')}  eval: {fc_usage.get('eval_tokens', '?')}",
                "[local — qwen2.5:7b, no API cost]",
                f"scene_summary: {meta.get('scene_summary', '(empty)')}",
            ])

        return resolved
