"""Prefetch cache — background generation of future node content.

Strategy (PRISM timing pattern adapted for Loombound):
  - When player enters Node N, trigger background generation of Node N+1 content.
  - Generation runs in a daemon thread while the player plays through Node N.
  - When _play_node loads Node N+1, it checks the cache first.
  - Cache hit  → use LLM-generated arbitration payloads instead of authored JSON.
  - Cache miss → fall back to authored JSON as before (no regression).

Thread model:
  play_cli is synchronous (blocking input). Background generation uses
  threading.Thread + asyncio.run() inside the thread, keeping the main loop
  unchanged. Thread is daemon so it does not block game exit.

Stale detection:
  If the player's state changed significantly between trigger and consumption,
  the cached content may no longer fit. PrefetchCache.consume() returns None
  if the entry is stale, letting the caller fall back to authored content.
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

from src.core.deterministic_kernel.models import CoreStateView, NodeSummary
from src.core.memory.m2_store import M2Store
from src.core.memory.types import NodeMemory, RunMemory

from .collector import build_classifier_input
from .fast_core import FastCoreExpander, FastCoreConfig
from .m2_classifier import M2Classifier
from .types import ArbitrationSeed, ArbitrationOptionSeed, NodeSeedPack, PrefetchEntry

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
    """Convert a Table A row into a Fast Core tendency payload."""

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
    arb_idx: int = 0,
    effects_by_arb: dict[int, dict[str, dict]] | None = None,
) -> ArbitrationSeed:
    """Blend a node skeleton from Table B with the runtime Table A tendency.

    effects_by_arb: {arb_idx: {option_id: {health_delta, money_delta, sanity_delta}}}
    When provided, these Opus-assigned values override Haiku's placeholder effects.
    """
    raw_options = skeleton.options or []
    arb_effects = (effects_by_arb or {}).get(arb_idx, {})
    arb_options = [
        ArbitrationOptionSeed(
            option_id=o.get("option_id", f"opt_{i}"),
            intent=o.get("intent", ""),
            tags=o.get("tags", []),
            # Opus-assigned effects take priority; fall back to Haiku placeholder
            effects=arb_effects.get(o.get("option_id", f"opt_{i}"), o.get("effects", {})),
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

    return ArbitrationSeed(
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
    """Manages background generation and retrieval of future node content.

    Usage in play_cli:
        cache = PrefetchCache()
        cache.warmup()                          # at game start

        # when entering node N:
        cache.trigger(next_node_id, run, node_history, arbitration_count)

        # when _play_node loads arbitrations for node N+1:
        resolved = cache.consume(node_id)
        if resolved:
            use resolved[i] instead of authored JSON
        else:
            fall back to authored JSON
    """

    def __init__(
        self,
        fast_cfg: FastCoreConfig | None = None,
        lang: str = "en",
        m2_classifier: M2Classifier | None = None,
    ) -> None:
        fast_cfg = fast_cfg or FastCoreConfig()
        fast_cfg.lang = lang
        self._fast = FastCoreExpander(fast_cfg)
        self._m2_classifier = m2_classifier
        self._cache: dict[str, PrefetchEntry] = {}
        self._m2_result: dict[str, int] = {}  # node_id → classified m2_id
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface (called from synchronous play_cli)
    # ------------------------------------------------------------------

    def warmup(self) -> None:
        """Warm up the local model in a background thread.

        Call once at game start so the first prefetch doesn't pay cold-start.
        """
        def _run() -> None:
            asyncio.run(self._fast.warmup())

        t = threading.Thread(target=_run, name="fastcore-warmup", daemon=True)
        t.start()

    def trigger(
        self,
        target_node_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        node_history: list[NodeSummary],
        arbitration_count: int,
        current_node_memory: NodeMemory | None = None,
    ) -> None:
        """Start background generation for target_node_id if not already running.

        Safe to call multiple times — ignores if entry already pending/ready.
        Always uses the preloaded path (M2Classifier + Table B). If Table B or
        M2 Classifier is unavailable the entry is marked failed and the caller
        falls back to authored JSON.
        """
        with self._lock:
            existing = self._cache.get(target_node_id)
            if existing and existing.status in ("pending", "ready"):
                log.debug("Prefetch: '%s' already %s, skipping trigger.",
                          target_node_id, existing.status)
                return
            entry = PrefetchEntry(node_id=target_node_id, status="pending")
            self._cache[target_node_id] = entry

        log.info("Prefetch: triggering background generation for '%s' (%d arbitration(s)).",
                 target_node_id, arbitration_count)

        # Deep-copy state so background thread doesn't race with main loop
        state_snapshot = copy.deepcopy(core_state)
        memory_snapshot = copy.deepcopy(run_memory)
        history_snapshot = copy.deepcopy(node_history)
        current_node_snapshot = copy.deepcopy(current_node_memory)

        def _run() -> None:
            asyncio.run(
                self._generate(
                    target_node_id,
                    state_snapshot,
                    memory_snapshot,
                    history_snapshot,
                    arbitration_count,
                    current_node_snapshot,
                )
            )

        t = threading.Thread(
            target=_run,
            name=f"prefetch-{target_node_id}",
            daemon=True,
        )
        t.start()

    def pop_m2_id(self, node_id: str) -> int | None:
        """Return and remove the M2 classification result for node_id, if any."""
        with self._lock:
            return self._m2_result.pop(node_id, None)

    def wait_for(self, node_id: str, timeout: float = 120.0) -> None:
        """Block until prefetch for node_id is no longer pending.

        Shows a simple progress indicator while waiting.
        Returns immediately if the entry doesn't exist or is already settled.
        """
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
        """Return resolved arbitration payloads if generation succeeded.

        Returns:
            list of arbitration JSON dicts (in order) if ready,
            None if pending, failed, stale, or not triggered.

        Read, status-check, and deletion are all performed inside a single
        lock acquisition to avoid TOCTOU between background thread status
        updates and the main thread's consumption.
        """
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
                self._m2_result.pop(node_id, None)
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

        # status == "ready"
        log.info("Prefetch: '%s' ready — using %d LLM-generated arbitration(s).",
                 node_id, arb_count)
        return resolved

    def invalidate(self, node_id: str) -> None:
        """Mark a cached entry as stale (e.g. after a major state change)."""
        with self._lock:
            entry = self._cache.get(node_id)
            if entry:
                entry.mark_stale()

    # ------------------------------------------------------------------
    # Internal async generation pipeline
    # ------------------------------------------------------------------

    async def _generate(
        self,
        target_node_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        node_history: list[NodeSummary],
        arbitration_count: int,
        current_node_memory: NodeMemory | None = None,
    ) -> None:
        try:
            if self._m2_classifier is None or not run_memory.m2.has_tables():
                reason = "m2_classifier not set" if self._m2_classifier is None else "table_a/table_b not loaded"
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
                node_history,
                arbitration_count,
                current_node_memory,
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

    # ------------------------------------------------------------------
    # Preloaded path: M2Classifier → Table B lookup → Fast Core expand
    # ------------------------------------------------------------------

    async def _classify_node(
        self,
        target_node_id: str,
        quasi: str,
        run_memory: RunMemory,
    ) -> tuple[int, dict[int, dict[str, dict]], Any, Any] | None:
        """Run M2 Classifier and resolve Table A + Table B entries.

        Stores the m2_id in self._m2_result and marks the cache entry as failed
        on any lookup miss. Returns (m2_id, arc_row, node_entry) on success,
        or None on any failure.
        """
        _md_log([
            f"## [{_ts()}] M2 CLASSIFIER REQUEST — node `{target_node_id}`",
            "```",
            quasi,
            "```",
        ])

        m2_id, effects_by_arb, m2_usage = await self._m2_classifier.classify(quasi, target_node_id)  # type: ignore[union-attr]
        _inp = m2_usage.get('input', 0)
        _out = m2_usage.get('output', 0)
        _cr  = m2_usage.get('cache_read', 0)
        _cc  = m2_usage.get('cache_created', 0)
        _cost  = _inp * _OPUS_INPUT_COST + _out * _OPUS_OUTPUT_COST + _cr * _OPUS_CACHE_READ_COST
        _saved = _cr * (_OPUS_INPUT_COST - _OPUS_CACHE_READ_COST)
        _md_log([
            f"## [{_ts()}] M2 CLASSIFIER RESPONSE — node `{target_node_id}` entry_id={m2_id}",
            f"tokens — input: {_inp}  output: {_out}  cache_created: {_cc}  cache_read: {_cr}",
            f"cost: ${_cost:.4f}  cache_savings: ${_saved:.4f}",
        ])

        with self._lock:
            self._m2_result[target_node_id] = m2_id

        def _fail(reason: str) -> None:
            with self._lock:
                entry = self._cache.get(target_node_id)
                if entry:
                    entry.mark_failed(reason)

        if m2_id < 0:
            log.warning("Prefetch[preloaded]: no-match for '%s' — authored fallback.", target_node_id)
            _fail("m2 no-match")
            return None

        arc_row = run_memory.m2.lookup_arc(m2_id)
        if arc_row is None:
            log.warning(
                "Prefetch[preloaded]: entry_id=%d not in Table A for '%s' — authored fallback.",
                m2_id, target_node_id,
            )
            _fail(f"table_a missing entry_id={m2_id}")
            return None

        node_entry = run_memory.m2.lookup_node(target_node_id)
        if node_entry is None or not node_entry.arbitrations:
            log.warning(
                "Prefetch[preloaded]: node_id='%s' not in Table B — authored fallback.",
                target_node_id,
            )
            _fail(f"table_b missing node_id={target_node_id}")
            return None

        _md_log([
            f"## [{_ts()}] TABLE B NODE SKELETON LOOKUP — node `{target_node_id}`",
            f"node_type: {node_entry.node_type}",
            f"label: {node_entry.label}",
            f"map_blurb: {node_entry.map_blurb}",
            f"arbitrations: {len(node_entry.arbitrations)}",
            f"effects assigned by opus: {sum(len(v) for v in effects_by_arb.values())} option(s)",
        ])
        _md_log([
            f"## [{_ts()}] RUNTIME ARC TENDENCY — node `{target_node_id}` entry_id={m2_id}",
            f"arc_trajectory: {arc_row.arc_trajectory}",
            f"world_pressure: {arc_row.world_pressure}",
            f"narrative_pacing: {arc_row.narrative_pacing}",
            f"pending_intent: {arc_row.pending_intent}",
        ])

        return m2_id, effects_by_arb, arc_row, node_entry

    async def _expand_arbitrations(
        self,
        seeds: list[ArbitrationSeed],
        node_id: str,
        id_prefix: str,
        core_state: CoreStateView,
    ) -> list[dict[str, Any]]:
        """Expand a list of ArbitrationSeeds via Fast Core; log each call.

        id_prefix is used for arb_id naming ("tb" for preloaded, "gen" for dynamic)
        and determines which extra fields appear in the RESPONSE log.
        """
        resolved: list[dict[str, Any]] = []
        for idx, arb_seed in enumerate(seeds):
            arb_id = f"{node_id}_{id_prefix}_{idx:02d}"
            payload, fc_usage = await self._fast.expand(arb_seed, core_state, arb_id)
            resolved.append(payload)

            ctx = payload.get("context", {})
            meta = ctx.get("metadata", {})
            log_resp: list[str] = [
                f"## [{_ts()}] FAST CORE RESPONSE ({id_prefix}) — `{arb_id}`",
                f"tokens — prompt: {fc_usage.get('prompt_tokens', '?')}  eval: {fc_usage.get('eval_tokens', '?')}",
                "[local — gemma3, no API cost]",
                f"scene_summary: {meta.get('scene_summary', '(empty)')}",
            ]
            if id_prefix == "gen":
                log_resp += [
                    f"sanity_question: {meta.get('sanity_question', '(empty)')}",
                    "options:",
                    *[
                        f"  - [{o.get('option_id')}] {o.get('label', '(no label)')}"
                        for o in payload.get("options", [])
                    ],
                ]
            _md_log(log_resp)

        return resolved

    async def _generate_preloaded(
        self,
        target_node_id: str,
        core_state: CoreStateView,
        run_memory: RunMemory,
        node_history: list[NodeSummary],
        arbitration_count: int,
        current_node_memory: NodeMemory | None = None,
    ) -> None:
        # Step 1: build classifier input and run M2 Classifier + table lookups
        quasi = build_classifier_input(
            core_state,
            run_memory,
            node_history,
            current_node_memory=current_node_memory,
        )

        result = await self._classify_node(target_node_id, quasi, run_memory)
        if result is None:
            return
        m2_id, effects_by_arb, arc_row, node_entry = result

        # Step 2: merge Table B skeletons with arc tendency and Opus-assigned effects
        merged_seeds: list[ArbitrationSeed] = []
        for idx in range(arbitration_count):
            skeleton = node_entry.arbitrations[min(idx, len(node_entry.arbitrations) - 1)]
            arb_seed = _merge_preloaded_seed(skeleton, arc_row, arb_idx=idx, effects_by_arb=effects_by_arb)
            merged_seeds.append(arb_seed)
            arb_id = f"{target_node_id}_tb_{idx:02d}"
            _md_log([
                f"## [{_ts()}] FAST CORE REQUEST (preloaded) — `{arb_id}`",
                f"scene_concept: {arb_seed.scene_concept}",
                f"sanity_axis: {arb_seed.sanity_axis}",
                f"tendency: {arb_seed.tendency}",
            ])

        # Step 3: Fast Core expands each arbitration
        resolved = await self._expand_arbitrations(merged_seeds, target_node_id, "tb", core_state)

        # Step 4: Assemble seed_pack and store in cache
        seed_pack = NodeSeedPack(
            target_node_id=target_node_id,
            node_theme=arc_row.arc_trajectory,
            narrative_direction=arc_row.pending_intent,
            arbitrations=merged_seeds,
        )

        with self._lock:
            entry = self._cache.get(target_node_id)
            if entry:
                entry.mark_ready(seed_pack, resolved)

        _md_log([
            f"## [{_ts()}] COMPLETE (preloaded) — `{target_node_id}` "
            f"({len(resolved)} arbitration(s), entry_id={m2_id})",
        ])
        log.info(
            "Prefetch[preloaded]: '%s' complete (%d arb(s), m2_id=%d).",
            target_node_id, len(resolved), m2_id,
        )

