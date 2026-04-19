"""Interactive CLI loop for playing a Loombound saga."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from src.shared.dotenv import load_dotenv
from src.t0.memory import append_node_event, update_after_waypoint
from src.t2.core import PrefetchCache
from src.t2.core.collector import build_classifier_input, build_scene_history_entry
from src.t0.core import (
    render_map_hud,
    render_node_header,
    render_run_complete,
    render_run_intro,
    render_input_panel,
    pause,
)
from src.runtime.play_runtime import (
    choose_index,
    make_run,
    resolve_asset_path,
)
from src.t0.core import (
    AssetValidationError,
    load_json_asset,
    validate_encounter_asset,
)
from src.runtime.play_encounter import _play_encounter
from src.runtime.saga_loader import load_saga_bundle
from src.runtime.play_bootstrap import parse_play_args, build_prefetch_cache


log = logging.getLogger(__name__)




def _parse_encounters(waypoint_spec: dict) -> tuple[int, list[dict]]:
    """Return (llm_count, authored_specs) from a waypoint spec's 'encounters' field.

    Two formats are supported:
      int   → LLM-generated mode; llm_count = that integer, authored_specs = []
      list  → Authored mode;      llm_count = 0, authored_specs = the list
    """
    field = waypoint_spec.get("encounters", [])
    if isinstance(field, int):
        return field, []
    return 0, field


def _play_waypoint(
    run,
    saga: dict[str, object],
    saga_waypoint: dict[str, object],
    rules,
    prefetch: PrefetchCache | None = None,
    saga_waypoint_id: str | None = None,
    narration_table: dict | None = None,
) -> object | None:
    depth: int = saga_waypoint["depth"]
    waypoint_type: str = saga_waypoint["waypoint_type"]
    waypoint_id = f"{saga_waypoint_id}:depth_{depth:02d}"

    run.core_state.depth = depth
    run.core_state.scene_type = waypoint_type

    waypoint = run.start_waypoint(waypoint_id=waypoint_id, waypoint_type=waypoint_type, depth=depth)
    append_node_event(waypoint.memory, "node_entered", waypoint_id=waypoint.waypoint_id, waypoint_type=waypoint.waypoint_type, depth=waypoint.depth)

    render_node_header(run, saga_waypoint)

    llm_count, authored_specs = _parse_encounters(saga_waypoint)
    total_arbs = llm_count or len(authored_specs)

    # Prefetch cache is keyed by saga waypoint ID (e.g. "night_market").
    cache_key = saga_waypoint_id or waypoint_id
    if prefetch:
        prefetch.wait_for(cache_key)
    prefetched = prefetch.consume(cache_key) if prefetch else None
    if prefetched is None and prefetch:
        err = prefetch.get_error(cache_key)
        if err:
            raise RuntimeError(
                f"Prefetch failed for waypoint '{cache_key}': {err}\n"
                "Check logs/llm.md for details."
            )

    if prefetched and len(prefetched) == total_arbs:
        payloads = prefetched
    elif llm_count > 0:
        raise RuntimeError(
            f"Prefetch unavailable for waypoint '{cache_key}' "
            f"({llm_count} LLM encounter(s) expected). "
            "Check logs/llm.md for generation errors."
        )
    else:
        payloads = [
            validate_encounter_asset(
                load_json_asset(resolve_asset_path(spec["file"])),
                source=resolve_asset_path(spec["file"]),
            )
            for spec in authored_specs
        ]

    for idx, payload in enumerate(payloads):
        _play_encounter(
            run, waypoint, payload, rules,
            prefetch, idx, saga_waypoint_id or waypoint_id, len(payloads),
            narration_table=narration_table,
        )

    waypoint.memory.waypoint_summary = f"{waypoint.waypoint_type}:{len(waypoint.memory.choices_made)}_encounters:sanity={waypoint.memory.sanity_lost_in_waypoint}"
    append_node_event(
        waypoint.memory,
        "node_finalized",
        waypoint_id=waypoint.waypoint_id,
        encounter_count=len(waypoint.memory.choices_made),
        sanity_lost=waypoint.memory.sanity_lost_in_waypoint,
    )
    update_after_waypoint(run.memory, waypoint.memory)
    run.memory.scene_history.push(build_scene_history_entry(run.core_state, run.memory, waypoint.memory))
    summary = waypoint.build_summary(sanity_delta=waypoint.memory.sanity_lost_in_waypoint)
    run.close_current_waypoint(summary=summary)
    return waypoint.memory


def _prefetch_targets(
    *,
    prefetch: PrefetchCache | None,
    saga: dict[str, object],
    target_ids: list[str],
    run,
) -> None:
    """Trigger prefetch for a list of saga waypoint IDs."""

    if prefetch is None:
        return

    seen: set[str] = set()
    for target_id in target_ids:
        if target_id in seen:
            continue
        seen.add(target_id)
        next_saga_waypoint = saga["waypoints"].get(target_id, {})
        try:
            llm_c, authored = _parse_encounters(next_saga_waypoint)
            arb_count = llm_c or len(authored)
            if arb_count:
                prefetch.trigger(
                    target_waypoint_id=target_id,
                    core_state=run.core_state,
                    run_memory=run.memory,
                    encounter_count=arb_count,
                )
        except (AssetValidationError, ValueError) as exc:
            log.warning("Prefetch: skipping '%s' — waypoint spec invalid: %s", target_id, exc)


def _collect_lookahead_targets(saga: dict[str, object], next_nodes: list[str]) -> list[str]:
    """Return unique grandchild saga waypoint IDs in stable order."""

    targets: list[str] = []
    seen: set[str] = set()
    nodes = saga.get("waypoints", {})
    for next_id in next_nodes:
        next_saga_waypoint = nodes.get(next_id, {})
        for lookahead_id in next_saga_waypoint.get("next_waypoints", []):
            if lookahead_id in seen:
                continue
            seen.add(lookahead_id)
            targets.append(lookahead_id)
    return targets


def main() -> None:
    load_dotenv()

    args = parse_play_args()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    bundle = load_saga_bundle(Path(args.saga))
    saga, saga_id_str = bundle.saga, bundle.saga_id
    rules = bundle.rules
    narration_table = bundle.narration_table

    if not rules:
        log.warning("No rules found for saga '%s' — rule selection disabled.", saga_id_str)
    if narration_table is not None:
        log.info("Loaded narration table: %d theme(s).", len(narration_table))

    run = make_run(saga)
    run.rule_system.set_templates(rules)
    run.memory.tables = bundle.tables

    fast_model = args.fast_model or os.environ.get("FAST_CORE_MODEL", "qwen2.5:7b")
    prefetch = build_prefetch_cache(bundle, api_key, args.lang, fast_model, saga.get("tone") or None)
    prefetch.warmup()

    current_waypoint_id = saga["start_waypoint_id"]

    # Prefetch the start waypoint while the player reads the intro.
    # The main loop only prefetches next_waypoints, so without this the first
    # LLM-mode waypoint would always have empty encounters.
    _prefetch_targets(
        prefetch=prefetch,
        saga=saga,
        target_ids=[current_waypoint_id],
        run=run,
    )

    render_run_intro(saga)
    pause("Press Enter to step onto the road...")
    nodes_played = 0
    try:
        while current_waypoint_id:
            saga_waypoint = saga["waypoints"][current_waypoint_id]

            # Determine next waypoints now so we can trigger prefetch for all of them
            next_waypoints = saga_waypoint.get("next_waypoints", [])

            # Trigger background generation for each candidate next waypoint
            if next_waypoints:
                _prefetch_targets(
                    prefetch=prefetch,
                    saga=saga,
                    target_ids=next_waypoints,
                    run=run,
                )

            _play_waypoint(
                run,
                saga,
                saga_waypoint,
                rules,
                prefetch=prefetch,
                saga_waypoint_id=current_waypoint_id,
                narration_table=narration_table,
            )
            nodes_played += 1

            if next_waypoints:
                lookahead_targets = _collect_lookahead_targets(saga, next_waypoints)
                _prefetch_targets(
                    prefetch=prefetch,
                    saga=saga,
                    target_ids=lookahead_targets,
                    run=run,
                )

            if not next_waypoints:
                break
            if args.nodes is not None and nodes_played >= args.nodes:
                break

            render_map_hud(run, saga, next_waypoints)
            render_input_panel("Choose your next destination")
            next_index = choose_index("> ", len(next_waypoints))
            current_waypoint_id = next_waypoints[next_index]

            # Trigger Opus for arb 0 of the chosen next waypoint.
            # Runs in background while the player reads the waypoint header + waits for C1.
            quasi = build_classifier_input(run.core_state, run.memory, list(run.waypoint_history))
            prefetch.update_arc_state(quasi, current_waypoint_id, 0)

    except KeyboardInterrupt:
        print("\n\nRun interrupted.")
        return
    except (AssetValidationError, ValueError) as exc:
        print(f"\n\nAsset error: {exc}")
        return
    except RuntimeError as exc:
        print(f"\n\nError: {exc}")
        return

    render_run_complete(run)


if __name__ == "__main__":
    main()
