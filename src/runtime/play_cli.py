"""Interactive CLI loop for playing a Loombound saga."""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
from pathlib import Path

from src.shared.dotenv import load_dotenv
from src.t0.memory import append_node_event, update_after_node
from src.t2.core import M2Classifier, M2ClassifierConfig, PrefetchCache
from src.t2.core.collector import build_classifier_input, build_a1_entry
from src.t1.core import C1Config
from src.t0.core import (
    render_map_hud,
    render_node_header,
    render_run_complete,
    render_run_intro,
    render_input_panel,
)
from src.runtime.saga import (
    REPO_ROOT,
    choose_index,
    load_rules,
    make_run,
    resolve_asset_path,
)
from src.t0.core import (
    AssetValidationError,
    load_json_asset,
    validate_encounter_asset,
)
from src.runtime.play_encounter import _overlay_effects, _play_encounter


log = logging.getLogger(__name__)

ARC_STATE_CATALOG_PATH = REPO_ROOT / "data" / "arc_state_catalog.json"




def _parse_encounters(node_spec: dict) -> tuple[int, list[dict]]:
    """Return (llm_count, authored_specs) from a node spec's 'encounters' field.

    Two formats are supported:
      int   → LLM-generated mode; llm_count = that integer, authored_specs = []
      list  → Authored mode;      llm_count = 0, authored_specs = the list
    """
    field = node_spec.get("encounters", [])
    if isinstance(field, int):
        return field, []
    return 0, field


def _play_node(
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

    waypoint.memory.node_summary = f"{waypoint.waypoint_type}:{len(waypoint.memory.choices_made)}_encounters:sanity={waypoint.memory.sanity_lost_in_node}"
    append_node_event(
        waypoint.memory,
        "node_finalized",
        waypoint_id=waypoint.waypoint_id,
        encounter_count=len(waypoint.memory.choices_made),
        sanity_lost=waypoint.memory.sanity_lost_in_node,
    )
    update_after_node(run.memory, waypoint.memory)
    run.memory.a1.push(build_a1_entry(run.core_state, run.memory, waypoint.memory))
    summary = waypoint.build_summary(sanity_delta=waypoint.memory.sanity_lost_in_node)
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
            log.warning("Prefetch: skipping '%s' — node spec invalid: %s", target_id, exc)


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

    parser = argparse.ArgumentParser(description="Play a Loombound saga. Requires ANTHROPIC_API_KEY and ollama (qwen2.5:7b).")
    parser.add_argument("--saga", type=Path, default=None, help="Path to a saga JSON file.")
    parser.add_argument("--nodes", type=int, default=None, metavar="N", help="Maximum number of nodes to play (default: unlimited).")
    parser.add_argument("--lang", choices=["en", "zh"], default="en", help="Generated content language (default: en).")
    parser.add_argument(
        "--fast",
        dest="fast_model",
        default=None,
        metavar="MODEL",
        help="Fast Core ollama model for text expansion (default: qwen2.5:7b). "
             "Can also be set via FAST_CORE_MODEL env var.",
    )
    args = parser.parse_args()

    if args.saga is None:
        sagas_dir = REPO_ROOT / "data" / "sagas"
        candidates = sorted(
            [p for p in sagas_dir.glob("*.json") if not p.stem.endswith(("_toll_lexicon", "_rules", "_narration_table"))],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ) if sagas_dir.exists() else []
        if not candidates:
            print(
                "No saga found. Generate one first:\n"
                "\n"
                "  ./loombound gen \"your theme\"\n"
                "\n"
                "Requires ANTHROPIC_API_KEY in .env.\n"
                "\n"
                "  cp .env.example .env   # then fill in ANTHROPIC_API_KEY",
                file=sys.stderr,
            )
            sys.exit(1)
        args.saga = candidates[0]
        print(f"No --saga specified. Using most recent: {candidates[0].stem}")

    # --- Startup check: Claude API key required ---
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "Error: ANTHROPIC_API_KEY is not set.\n"
            "Loombound requires a Claude API key to run.\n"
            "Set it in .env: ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.WARNING,
        format="\033[2m[%(levelname)s %(name)s] %(message)s\033[0m",
    )

    saga = load_json_asset(args.saga)
    saga_id_str = saga.get("saga_id", "")
    sagas_dir = REPO_ROOT / "data" / "sagas"

    _rules_path = sagas_dir / f"{saga_id_str}_rules.json"
    rules = load_rules(_rules_path) if _rules_path.exists() else []
    if not rules:
        log.warning("No rules found for saga '%s' — rule selection disabled.", saga_id_str)

    run = make_run(saga)
    run.rule_system.set_templates(rules)

    fast_model = (
        args.fast_model
        or os.environ.get("FAST_CORE_MODEL", "qwen2.5:7b")
    )
    fast_cfg = C1Config(
        model=fast_model,
        lang=args.lang,
        tone=saga.get("tone") or None,
    )

    # Load arc-state catalog (A2) and scene skeletons (A1) if available
    saga_dir = REPO_ROOT / "data" / "waypoints" / saga_id_str
    scene_skeletons_path = saga_dir / "scene_skeletons.json"

    if ARC_STATE_CATALOG_PATH.exists():
        run.memory.tables.load_arc_state_catalog(ARC_STATE_CATALOG_PATH)
    if scene_skeletons_path.exists():
        run.memory.tables.load_scene_skeletons(scene_skeletons_path)

    narration_table: dict | None = None
    _narration_path = sagas_dir / f"{saga_id_str}_narration_table.json"
    if _narration_path.exists():
        narration_table = json.loads(_narration_path.read_text(encoding="utf-8"))
        log.info("Loaded narration table: %d theme(s).", len(narration_table))

    # Build M2Classifier if arc-state catalog is loaded (provides the cached prefix)
    m2_classifier: M2Classifier | None = None
    if run.memory.tables.arc_state_catalog:
        saga_id = saga.get("saga_id", "")
        toll_lexicon_path = sagas_dir / f"{saga_id}_toll_lexicon.json"
        toll_lexicon = json.loads(toll_lexicon_path.read_text(encoding="utf-8")) if toll_lexicon_path.exists() else []
        toll_lexicon_json = json.dumps(toll_lexicon, ensure_ascii=False) if toll_lexicon else ""
        rules_json = json.dumps({"rules": [dataclasses.asdict(r) for r in rules]}, ensure_ascii=False)
        m2_cfg = M2ClassifierConfig(api_key=api_key)
        m2_classifier = M2Classifier(
            config=m2_cfg,
            arc_state_catalog_json=run.memory.tables.arc_state_catalog_json(),
            scene_option_index_json=run.memory.tables.scene_option_index_json() if run.memory.tables.scene_skeletons else "",
            toll_lexicon_json=toll_lexicon_json,
            rules_json=rules_json,
        )

    prefetch = PrefetchCache(fast_cfg=fast_cfg, lang=args.lang, m2_classifier=m2_classifier)
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

            _play_node(
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
