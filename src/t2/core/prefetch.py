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
  - Effects are stored keyed by "node_id:arb_idx" and consumed by play_cli just
    before displaying the target encounter.
  - gemma3 prefetch reads _current_arc_id directly — no Opus call needed.

Thread model:
  play_cli is synchronous (blocking input). Background generation uses
  threading.Thread + asyncio.run() inside the thread, keeping the main loop
  unchanged. Thread is daemon so it does not block game exit.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.t0.memory.models import CoreStateView, NarrationBlock, WaypointSummary
from src.t2.memory.a2_store import A2Store
from src.t0.memory.types import WaypointMemory, RunMemory

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.t1.core.fast_core import FastCoreExpander, FastCoreConfig
from .m2_classifier import M2Classifier
from .types import EncounterSeed, EncounterOptionSeed, NodeSeedPack, PrefetchEntry

log = logging.getLogger(__name__)

_OPUS_INPUT_COST       = 5.0  / 1_000_000
_OPUS_OUTPUT_COST      = 25.0 / 1_000_000
_OPUS_CACHE_READ_COST  = 0.50 / 1_000_000  # 10% of input rate
_HAIKU_INPUT_COST      = 0.80 / 1_000_000
_HAIKU_OUTPUT_COST     = 4.0  / 1_000_000

_REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).parents[3]
)
_LOG_FILE = _REPO_ROOT / "logs" / "llm.md"
_log_lock = threading.Lock()


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _md_log(lines: list[str]) -> None:
    """Append a fenced block to logs/llm.md. Thread-safe."""
    block = "\n".join(lines) + "\n\n"
    with _log_lock:
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(block)


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

    1. Node content prefetch (gemma3):
       trigger() → background thread generates encounter payloads for a future node.
       consume() → returns payloads (or None on cache miss/failure).

    2. Per-choice arc updates (Opus M2):
       update_arc_state() → after each player choice, fires async Opus call.
       consume_arb_effects() → blocks briefly for Opus result, returns option effects.
       _current_arc_id property → latest classified T2 cache entry_id.
    """

    def __init__(
        self,
        fast_cfg: "FastCoreConfig | None" = None,
        lang: str = "en",
        m2_classifier: M2Classifier | None = None,
    ) -> None:
        from src.t1.core.fast_core import FastCoreExpander, FastCoreConfig
        fast_cfg = fast_cfg or FastCoreConfig()
        fast_cfg.lang = lang
        self._fast = FastCoreExpander(fast_cfg)
        self._m2_classifier = m2_classifier

        # Node content cache
        self._cache: dict[str, PrefetchEntry] = {}
        self._lock = threading.Lock()

        # Per-choice arc state tracking
        self._current_arc_id: int = 0   # updated after each Opus response
        self._pending_effects: dict[str, dict[str, dict]] = {}  # "node:arb" → effects_map
        self._pending_rule_ids: dict[str, str] = {}             # "node:arb" → rule_id
        self._effects_events: dict[str, threading.Event] = {}   # "node:arb" → Event
        self._arc_lock = threading.Lock()

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
        target_node_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        waypoint_history: list[WaypointSummary],
        encounter_count: int,
        current_waypoint_memory: WaypointMemory | None = None,
    ) -> None:
        """Start background generation for target_node_id if not already running.

        Uses the preloaded path: T1 cache skeleton + current _current_arc_id tendency
        → gemma3 expansion. If T1 cache is unavailable, marks the entry as failed
        and the caller falls back to authored JSON.
        """
        with self._lock:
            existing = self._cache.get(target_node_id)
            if existing and existing.status in ("pending", "ready"):
                log.debug("Prefetch: '%s' already %s, skipping trigger.",
                          target_node_id, existing.status)
                return
            entry = PrefetchEntry(node_id=target_node_id, status="pending")
            self._cache[target_node_id] = entry

        log.info("Prefetch: triggering background generation for '%s' (%d encounter(s)).",
                 target_node_id, encounter_count)

        # Snapshot the arc_id at trigger time — gemma3 uses this for tendency
        arc_id_snapshot = self._current_arc_id

        # Deep-copy state so background thread doesn't race with main loop
        state_snapshot = copy.deepcopy(core_state)
        memory_snapshot = copy.deepcopy(run_memory)

        def _run() -> None:
            asyncio.run(
                self._generate(
                    target_node_id,
                    state_snapshot,
                    memory_snapshot,
                    encounter_count,
                    arc_id_snapshot,
                )
            )

        t = threading.Thread(
            target=_run,
            name=f"prefetch-{target_node_id}",
            daemon=True,
        )
        t.start()

    def wait_for(self, node_id: str, timeout: float = 120.0) -> None:
        """Block until prefetch for node_id is no longer pending."""
        with self._lock:
            entry = self._cache.get(node_id)
        if entry is None or entry.status != "pending":
            return

        deadline = time.monotonic() + timeout
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        print(f"\033[2m", end="", file=sys.stderr)
        try:
            while time.monotonic() < deadline:
                with self._lock:
                    entry = self._cache.get(node_id)
                if entry is None or entry.status != "pending":
                    break
                print(f"\r{spinner[idx % len(spinner)]} generating content...",
                      end="", file=sys.stderr, flush=True)
                idx += 1
                time.sleep(0.3)
        finally:
            print(f"\r\033[0m\033[K", end="", file=sys.stderr, flush=True)

    def consume(self, node_id: str) -> list[dict[str, Any]] | None:
        """Return resolved encounter payloads if generation succeeded."""
        with self._lock:
            entry = self._cache.get(node_id)
            if entry is None:
                log.debug("Prefetch: no entry for '%s' — authored fallback.", node_id)
                return None

            status = entry.status
            error = entry.error
            if status == "ready":
                resolved = list(entry.resolved)
                arb_count = len(resolved)
                del self._cache[node_id]
            else:
                resolved = None
                arb_count = 0

        if status == "pending":
            log.info("Prefetch: '%s' still generating — authored fallback.", node_id)
            return None
        if status == "failed":
            log.warning("Prefetch: '%s' generation failed (%s) — authored fallback.",
                        node_id, error)
            return None
        if status == "stale":
            log.info("Prefetch: '%s' is stale — authored fallback.", node_id)
            return None

        log.info("Prefetch: '%s' ready — using %d LLM-generated encounter(s).",
                 node_id, arb_count)
        return resolved

    def invalidate(self, node_id: str) -> None:
        """Mark a cached entry as stale (e.g. after a major state change)."""
        with self._lock:
            entry = self._cache.get(node_id)
            if entry:
                entry.mark_stale()

    # ------------------------------------------------------------------
    # Public interface — per-choice arc state updates
    # ------------------------------------------------------------------

    def update_arc_state(
        self,
        quasi: str,
        next_node_id: str | None,
        next_arb_idx: int | None,
    ) -> None:
        """Fire-and-forget Opus call after each player choice.

        Args:
            quasi:         Current game state description (build_classifier_input output).
            next_node_id:  Node the next encounter belongs to.
                           None = last arb of a node transition (effects not needed yet).
            next_arb_idx:  0-based index of the next encounter in next_node_id.
                           None = no next arb in same node (only update entry_id).

        Both must be non-None to produce effects. If either is None, Opus still
        classifies the arc state (updates _current_arc_id) but returns no effects.
        """
        if self._m2_classifier is None:
            return

        effects_key: str | None = None
        if next_node_id is not None and next_arb_idx is not None:
            effects_key = f"{next_node_id}:{next_arb_idx}"
            with self._arc_lock:
                event = threading.Event()
                self._effects_events[effects_key] = event

        quasi_copy = quasi  # string is immutable, no deep copy needed

        def _run() -> None:
            asyncio.run(self._run_arc_update(quasi_copy, next_node_id, next_arb_idx, effects_key))

        t = threading.Thread(
            target=_run,
            name=f"m2-{next_node_id}-{next_arb_idx}",
            daemon=True,
        )
        t.start()

    def consume_arb_effects(
        self,
        node_id: str,
        arb_idx: int,
        timeout: float = 8.0,
    ) -> tuple[dict[str, dict], str]:
        """Wait for and consume M2-assigned effects and rule selection for a specific encounter.

        Returns (effects_map, selected_rule_id).
        effects_map: {option_id: {"health_delta": int, "money_delta": int, "sanity_delta": int}}
        selected_rule_id: rule id string, or "" if M2 selected none.
        Both are empty/blank on cache miss or timeout.
        """
        effects_key = f"{node_id}:{arb_idx}"

        with self._arc_lock:
            event = self._effects_events.get(effects_key)

        if event is not None:
            event.wait(timeout=timeout)

        with self._arc_lock:
            effects = self._pending_effects.pop(effects_key, {})
            rule_id = self._pending_rule_ids.pop(effects_key, "")
            self._effects_events.pop(effects_key, None)

        if not effects:
            log.debug("Prefetch: no M2 effects for '%s' arb %d.", node_id, arb_idx)
        else:
            log.info("Prefetch: consumed M2 effects for '%s' arb %d (%d option(s)) rule=%r.",
                     node_id, arb_idx, len(effects), rule_id)
        return effects, rule_id

    def start_narration_rewrite(
        self,
        opening_draft: str,
        judgement_draft: str,
        warning_draft: str,
        scene_summary: str,
        scene_type: str,
        rule_theme: str,
    ) -> tuple[threading.Event, list]:
        """Start a background T1 narration rewrite.

        Returns (done_event, result_container).
        result_container is a 1-item list; result_container[0] is the NarrationBlock
        once done_event is set. Falls back to the draft on failure.
        """
        done = threading.Event()
        result: list = [None]

        def _run() -> None:
            import asyncio
            try:
                block = asyncio.run(self._fast.rewrite_narration(
                    opening_draft, judgement_draft, warning_draft,
                    scene_summary, scene_type, rule_theme,
                ))
                result[0] = block
            except Exception as exc:
                log.warning("Narration rewrite thread failed: %s", exc)
                result[0] = NarrationBlock(
                    opening=opening_draft,
                    judgement=judgement_draft,
                    warning=warning_draft,
                )
            finally:
                done.set()

        t = threading.Thread(target=_run, name="narration-rewrite", daemon=True)
        t.start()
        return done, result

    # ------------------------------------------------------------------
    # Internal: Opus arc update
    # ------------------------------------------------------------------

    async def _run_arc_update(
        self,
        quasi: str,
        next_node_id: str | None,
        next_arb_idx: int | None,
        effects_key: str | None,
    ) -> None:
        """Call M2Classifier, update _current_arc_id, store effects."""
        label = f"{next_node_id}:{next_arb_idx}" if next_node_id else "entry_id_only"
        _md_log([
            f"## [{_ts()}] M2 ARC UPDATE REQUEST — {label}",
            "```",
            quasi,
            "```",
        ])

        try:
            entry_id, rule_id, effects_map, usage = await self._m2_classifier.classify(  # type: ignore[union-attr]
                quasi,
                next_node_id=next_node_id,
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

    # ------------------------------------------------------------------
    # Internal async generation pipeline — preloaded path
    # ------------------------------------------------------------------

    async def _generate(
        self,
        target_node_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        encounter_count: int,
        arc_id_snapshot: int,
    ) -> None:
        try:
            if not run_memory.a2.has_caches():
                reason = "a2_cache_table/a1_cache_table not loaded"
                log.warning("Prefetch: '%s' skipped — %s.", target_node_id, reason)
                with self._lock:
                    entry = self._cache.get(target_node_id)
                    if entry:
                        entry.mark_failed(reason)
                return
            await self._generate_preloaded(
                target_node_id,
                core_state,
                run_memory,
                encounter_count,
                arc_id_snapshot,
            )
        except Exception as exc:
            tb = traceback.format_exc()
            _md_log([
                f"## [{_ts()}] FAILED — `{target_node_id}`",
                f"error: {exc}",
                "```",
                tb,
                "```",
            ])
            log.error("Prefetch: '%s' generation failed: %s", target_node_id, exc, exc_info=True)
            with self._lock:
                entry = self._cache.get(target_node_id)
                if entry:
                    entry.mark_failed(str(exc))

    async def _generate_preloaded(
        self,
        target_node_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        encounter_count: int,
        arc_id_snapshot: int,
    ) -> None:
        """Preloaded path: look up T2 cache + T1 cache, expand with Fast Core.

        No Haiku call here — arc tendency comes from arc_id_snapshot which was
        captured at trigger() time from _current_arc_id.
        """
        # Step 1: T2 cache lookup for arc tendency
        arc_row = run_memory.a2.lookup_arc(arc_id_snapshot)
        if arc_row is None:
            # Fallback to entry 0 if snapshot id is missing
            arc_row = run_memory.a2.lookup_arc(0)
        if arc_row is None:
            reason = f"a2_cache_table missing entry_id={arc_id_snapshot} and no entry 0"
            log.warning("Prefetch[preloaded]: '%s' — %s.", target_node_id, reason)
            with self._lock:
                entry = self._cache.get(target_node_id)
                if entry:
                    entry.mark_failed(reason)
            return

        # Step 2: T1 cache lookup
        node_entry = run_memory.a2.lookup_waypoint(target_node_id)
        if node_entry is None or not node_entry.encounters:
            reason = f"a1_cache_table missing waypoint_id={target_node_id}"
            log.warning("Prefetch[preloaded]: '%s' — %s.", target_node_id, reason)
            with self._lock:
                entry = self._cache.get(target_node_id)
                if entry:
                    entry.mark_failed(reason)
            return

        _md_log([
            f"## [{_ts()}] T1 CACHE LOOKUP — node `{target_node_id}` (arc_id={arc_id_snapshot})",
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
            arb_id = f"{target_node_id}_t1_{idx:02d}"
            _md_log([
                f"## [{_ts()}] FAST CORE REQUEST (preloaded) — `{arb_id}`",
                f"scene_concept: {arb_seed.scene_concept}",
                f"sanity_axis: {arb_seed.sanity_axis}",
                f"tendency: {arb_seed.tendency}",
            ])

        # Step 4: Fast Core expands each encounter
        resolved = await self._expand_arbitrations(merged_seeds, target_node_id, "t1", core_state)

        # Step 5: Assemble seed_pack and store in cache
        seed_pack = NodeSeedPack(
            target_node_id=target_node_id,
            node_theme=arc_row.arc_trajectory,
            narrative_direction=arc_row.pending_intent,
            encounters=merged_seeds,
        )

        with self._lock:
            entry = self._cache.get(target_node_id)
            if entry:
                entry.mark_ready(seed_pack, resolved)

        _md_log([
            f"## [{_ts()}] COMPLETE (preloaded) — `{target_node_id}` "
            f"({len(resolved)} encounter(s), arc_id={arc_id_snapshot})",
        ])
        log.info(
            "Prefetch[preloaded]: '%s' complete (%d arb(s), arc_id=%d).",
            target_node_id, len(resolved), arc_id_snapshot,
        )

    async def _expand_arbitrations(
        self,
        seeds: list[EncounterSeed],
        node_id: str,
        id_prefix: str,
        core_state: CoreStateView,
    ) -> list[dict[str, Any]]:
        """Expand a list of EncounterSeeds via Fast Core; log each call."""
        resolved: list[dict[str, Any]] = []
        for idx, arb_seed in enumerate(seeds):
            arb_id = f"{node_id}_{id_prefix}_{idx:02d}"
            payload, fc_usage = await self._fast.expand(arb_seed, core_state, arb_id)
            resolved.append(payload)

            ctx = payload.get("context", {})
            meta = ctx.get("metadata", {})
            _md_log([
                f"## [{_ts()}] FAST CORE RESPONSE ({id_prefix}) — `{arb_id}`",
                f"tokens — prompt: {fc_usage.get('prompt_tokens', '?')}  eval: {fc_usage.get('eval_tokens', '?')}",
                "[local — gemma3, no API cost]",
                f"scene_summary: {meta.get('scene_summary', '(empty)')}",
            ])

        return resolved
