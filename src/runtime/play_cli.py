"""Interactive CLI loop for playing a Loombound saga."""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
from pathlib import Path

from src.t0.memory import EncounterResult
from src.t0.core import apply_option_effects, enforce_rule
from src.t2.core import M2Classifier, M2ClassifierConfig, PrefetchCache
from src.t2.core.collector import build_classifier_input, build_a1_entry
from src.t1.core import C1Config
from src.t0.memory import append_node_event, record_choice, update_after_node
from src.t0.memory.models import NarrationBlock
from src.t0.core import (
    pause,
    render_encounter_view,
    render_choices,
    render_input_panel,
    render_map_hud,
    render_node_header,
    render_result,
    render_run_complete,
    render_run_intro,
)
from src.t0.core import build_selection_trace, evaluate_rules, select_rule
from src.runtime.saga import (
    REPO_ROOT,
    choose_index,
    load_rules,
    make_run,
    resolve_asset_path,
    sync_encounter_resources,
)
from src.t0.core import build_signals
from src.t0.core import (
    AssetValidationError,
    load_json_asset,
    validate_encounter_asset,
)


log = logging.getLogger(__name__)

T2_CACHE_PATH = REPO_ROOT / "data" / "a2_cache_table.json"




# ---------------------------------------------------------------------------
# .env loader (no external dependency needed)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from .env at repo root into os.environ.

    Uses os.environ.setdefault so existing shell exports are never overwritten.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)



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


def _overlay_effects(payload: dict, opus_effects: dict[str, dict]) -> None:
    """Patch Opus-assigned numeric effect values into a payload's option metadata in-place.

    Only the three stat keys are touched; add_events / add_marks written by
    C1-generated content is preserved. The payload dict is mutated directly.
    """
    for opt in payload.get("options", []):
        opt_id = opt.get("option_id", "")
        if opt_id in opus_effects:
            eff = opt.setdefault("metadata", {}).setdefault("effects", {})
            for key in ("health_delta", "money_delta", "sanity_delta"):
                eff[key] = opus_effects[opt_id].get(key, 0)
            toll = opus_effects[opt_id].get("toll", "")
            if toll:
                opt["toll"] = toll


def _play_encounter(
    run,
    waypoint,
    payload: dict[str, object],
    rules,
    prefetch: PrefetchCache | None,
    arb_idx: int,
    saga_waypoint_id: str,
    total_arbs: int,
    narration_table: dict | None = None,
) -> None:
    # Consume M2-assigned effects and rule selection (may be empty on cache miss)
    m2_effects: dict[str, dict] = {}
    m2_rule_id: str = ""
    if prefetch is not None:
        m2_effects, m2_rule_id = prefetch.consume_arb_effects(saga_waypoint_id, arb_idx)
        if m2_effects:
            _overlay_effects(payload, m2_effects)

    encounter = waypoint.load_current_encounter(payload)
    sync_encounter_resources(run, encounter)
    append_node_event(
        waypoint.memory,
        "encounter_loaded",
        encounter_id=encounter.encounter_id,
        scene_type=encounter.context.scene_type,
        context_id=encounter.context.context_id,
    )

    signals = build_signals(encounter)
    evaluations = evaluate_rules(encounter, rules)
    waypoint.rule_state.reset_for_encounter()
    waypoint.rule_state.record_evaluations(evaluations)

    # M2 rule selection is primary; deterministic evaluation is the fallback.
    m2_rule = next((r for r in rules if r.id == m2_rule_id), None) if m2_rule_id else None
    selected = (
        type("_Sel", (), {"rule": m2_rule})()  # lightweight wrapper matching select_rule output
        if m2_rule else
        select_rule(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    )

    waypoint.rule_state.record_selected_rule(selected.rule.id if selected else None)
    waypoint.rule_state.record_selection_trace(
        build_selection_trace(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    )
    run.rule_system.record_selected_rule(selected.rule.id if selected else None)
    append_node_event(
        waypoint.memory,
        "rule_selected",
        encounter_id=encounter.encounter_id,
        selected_rule_id=selected.rule.id if selected else None,
        matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
        source="m2" if m2_rule else "kernel",
    )

    option_results = enforce_rule(encounter, selected.rule if selected else None)

    rule_theme = selected.rule.theme if selected else "neutral"
    narration_text = ""
    if narration_table is not None:
        narration_text = (
            narration_table.get(rule_theme)
            or narration_table.get("neutral")
            or ""
        )

    render_encounter_view(run, encounter, selected.rule if selected else None)
    render_choices(option_results)
    render_input_panel("Choose an option")

    choice_index = choose_index("> ", len(option_results))
    chosen_result = option_results[choice_index]
    encounter.select_option(chosen_result.option_id)
    selected_option = encounter.get_option(chosen_result.option_id) or {}

    record_choice(
        waypoint.memory,
        encounter=encounter,
        selected_rule_id=selected.rule.id if selected else None,
        selected_rule_theme=selected.rule.theme if selected else None,
        selected_result=chosen_result,
    )
    append_node_event(
        waypoint.memory,
        "option_chosen",
        encounter_id=encounter.encounter_id,
        option_id=chosen_result.option_id,
        toll=chosen_result.toll,
        sanity_delta=chosen_result.sanity_cost,
    )

    # Fire-and-forget Opus call: updates arc entry_id + assigns effects for next arb.
    # Within a node: next_node_id = saga_waypoint_id, next_arb_idx = arb_idx + 1.
    # Last arb of a node: pass None/None — only entry_id is updated; the main loop
    # triggers the Opus call for the first arb of the chosen next node.
    if prefetch is not None:
        _is_last = arb_idx >= total_arbs - 1
        _next_node = saga_waypoint_id if not _is_last else None
        _next_idx  = arb_idx + 1       if not _is_last else None
        quasi = build_classifier_input(
            run.core_state, run.memory, list(run.waypoint_history),
            current_waypoint_memory=waypoint.memory,
        )
        prefetch.update_arc_state(quasi, _next_node, _next_idx)

    narration = NarrationBlock(text=narration_text)
    applied_notes = apply_option_effects(run, selected_option, chosen_result)
    encounter.set_result(
        EncounterResult(
            selected_rule_id=selected.rule.id if selected else None,
            matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
            option_results=option_results,
            sanity_delta=chosen_result.sanity_cost,
            narration=narration,
        )
    )
    encounter.mark_applied()
    waypoint.close_current_encounter()
    append_node_event(
        waypoint.memory,
        "encounter_finalized",
        encounter_id=encounter.encounter_id,
        selected_rule_id=selected.rule.id if selected else None,
        player_choice=chosen_result.option_id,
    )

    render_result(run, chosen_result, narration, applied_notes)
    pause()


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
    current_waypoint_memory=None,
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
                    waypoint_history=list(run.waypoint_history),
                    encounter_count=arb_count,
                    current_waypoint_memory=current_waypoint_memory,
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
    _load_dotenv()

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
    campaigns_dir_rt = REPO_ROOT / "data" / "sagas"

    _rules_path = campaigns_dir_rt / f"{saga_id_str}_rules.json"
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

    # Load T2 cache (arc palette) and T1 cache (node skeletons) if available
    saga_dir = REPO_ROOT / "data" / "waypoints" / saga_id_str
    a1_cache_table_path = saga_dir / "a1_cache_table.json"

    if T2_CACHE_PATH.exists():
        run.memory.a2.load_a2_cache_table(T2_CACHE_PATH)
    if a1_cache_table_path.exists():
        run.memory.a2.load_a1_cache_table(a1_cache_table_path)

    narration_table: dict | None = None
    _narration_path = campaigns_dir_rt / f"{saga_id_str}_narration_table.json"
    if _narration_path.exists():
        narration_table = json.loads(_narration_path.read_text(encoding="utf-8"))
        log.info("Loaded narration table: %d theme(s).", len(narration_table))

    # Build M2Classifier if A2 cache is loaded (provides the cached prefix)
    m2_classifier: M2Classifier | None = None
    if run.memory.a2.a2_cache_table:
        saga_id = saga.get("saga_id", "")
        campaigns_dir = REPO_ROOT / "data" / "sagas"
        toll_lexicon_path = campaigns_dir / f"{saga_id}_toll_lexicon.json"
        toll_lexicon = json.loads(toll_lexicon_path.read_text(encoding="utf-8")) if toll_lexicon_path.exists() else []
        toll_lexicon_json = json.dumps(toll_lexicon, ensure_ascii=False) if toll_lexicon else ""
        rules_json = json.dumps({"rules": [dataclasses.asdict(r) for r in rules]}, ensure_ascii=False)
        m2_cfg = M2ClassifierConfig(api_key=api_key)
        m2_classifier = M2Classifier(
            config=m2_cfg,
            a2_cache_table_json=run.memory.a2.a2_cache_table_prompt_json(),
            a1_cache_table_index_json=run.memory.a2.a1_cache_table_index_json() if run.memory.a2.a1_cache_table else "",
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

            completed_node_memory = _play_node(
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
                    current_waypoint_memory=completed_node_memory,
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
