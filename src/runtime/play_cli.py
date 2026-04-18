"""Interactive CLI loop for playing a small Loombound campaign."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys
from pathlib import Path

from src.t2.core import load_rules, load_templates
from src.t0.memory import EncounterResult
from src.t0.core import apply_option_effects, enforce_rule
from src.t2.core import M2Classifier, M2ClassifierConfig, PrefetchCache
from src.t2.core.collector import build_classifier_input, build_a1_entry
from src.t1.core.fast_core import FastCoreConfig
from src.t0.memory import append_node_event, record_choice, update_after_node
from src.t1.core import render_narration
from src.t0.core import (
    pause,
    render_arbitration_view,
    render_choices,
    render_input_panel,
    render_map_hud,
    render_node_header,
    render_result,
    render_run_complete,
    render_run_intro,
)
from src.t0.core import build_selection_trace, evaluate_rules, select_rule
from src.runtime.campaign import (
    REPO_ROOT,
    choose_index,
    make_run,
    resolve_asset_path,
    sync_encounter_resources,
)
from src.t0.core import build_signals, score_themes
from src.t0.core import (
    AssetValidationError,
    load_json_asset,
    validate_arbitration_asset,
)


log = logging.getLogger(__name__)

RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.small.json"
TEXT_PATH = REPO_ROOT / "data" / "text" / "narration_templates.json"
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
    gemma3 are preserved. The payload dict is mutated directly.
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
    templates: dict[str, list[str]],
    rules,
    prefetch: PrefetchCache | None,
    arb_idx: int,
    saga_waypoint_id: str,
    total_arbs: int,
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
        "arbitration_loaded",
        encounter_id=encounter.encounter_id,
        scene_type=encounter.context.scene_type,
        context_id=encounter.context.context_id,
    )

    signals = build_signals(encounter)
    theme_scores = score_themes(encounter, signals)
    evaluations = evaluate_rules(encounter, rules, theme_scores)
    waypoint.rule_state.reset_for_arbitration()
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
    narration = render_narration(
        encounter=encounter,
        rule=selected.rule if selected else None,
        templates=templates,
        enabled=True,
    )

    render_arbitration_view(run, encounter, selected.rule if selected else None)
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

    applied_notes = apply_option_effects(run, selected_option, chosen_result)
    encounter.set_result(
        EncounterResult(
            selected_rule_id=selected.rule.id if selected else None,
            matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
            option_results=option_results,
            sanity_delta=chosen_result.sanity_cost,
            theme_scores=theme_scores,
            narration=narration,
        )
    )
    encounter.mark_applied()
    waypoint.close_current_encounter()
    append_node_event(
        waypoint.memory,
        "arbitration_finalized",
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
    templates: dict[str, list[str]],
    prefetch: PrefetchCache | None = None,
    saga_waypoint_id: str | None = None,
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

    # Prefetch cache is keyed by campaign node ID (e.g. "night_market").
    cache_key = saga_waypoint_id or waypoint_id
    if prefetch:
        prefetch.wait_for(cache_key)
    prefetched = prefetch.consume(cache_key) if prefetch else None

    if prefetched and len(prefetched) == total_arbs:
        payloads = prefetched
    elif llm_count > 0:
        payloads = []
    else:
        payloads = [
            validate_arbitration_asset(
                load_json_asset(resolve_asset_path(spec["file"])),
                source=resolve_asset_path(spec["file"]),
            )
            for spec in authored_specs
        ]

    for idx, payload in enumerate(payloads):
        _play_encounter(
            run, waypoint, payload, templates, rules,
            prefetch, idx, saga_waypoint_id or waypoint_id, len(payloads),
        )

    waypoint.memory.node_summary = f"{waypoint.waypoint_type}:{len(waypoint.memory.choices_made)}_arbitrations:sanity={waypoint.memory.sanity_lost_in_node}"
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
    """Trigger prefetch for a list of campaign node IDs."""

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
                    target_node_id=target_id,
                    core_state=run.core_state,
                    run_memory=run.memory,
                    waypoint_history=list(run.waypoint_history),
                    encounter_count=arb_count,
                    current_waypoint_memory=current_waypoint_memory,
                )
        except (AssetValidationError, ValueError) as exc:
            log.warning("Prefetch: skipping '%s' — node spec invalid: %s", target_id, exc)


def _collect_lookahead_targets(saga: dict[str, object], next_nodes: list[str]) -> list[str]:
    """Return unique grandchild campaign node IDs in stable order."""

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

    parser = argparse.ArgumentParser(description="Play a Loombound campaign. Requires ANTHROPIC_API_KEY and ollama (gemma3:4b).")
    parser.add_argument("--saga", type=Path, default=None, help="Path to a campaign JSON file.")
    parser.add_argument("--nodes", type=int, default=None, metavar="N", help="Maximum number of nodes to play (default: unlimited).")
    parser.add_argument("--lang", choices=["en", "zh"], default="en", help="Generated content language (default: en).")
    parser.add_argument(
        "--fast",
        dest="fast_model",
        default=None,
        metavar="MODEL",
        help="Fast Core ollama model for text expansion (default: gemma3:4b). "
             "Can also be set via FAST_CORE_MODEL env var.",
    )
    args = parser.parse_args()

    if args.saga is None:
        print(
            "No campaign found. Generate one first:\n"
            "\n"
            "  ./loombound gen \"your theme\"\n"
            "\n"
            "Requires ANTHROPIC_API_KEY in .env.\n"
            "\n"
            "With Haiku M2 + local gemma3 (Fast Core), a typical 5-node run costs ~$0.01.\n"
            "Replacing Fast Core with Opus alone would cost ~$0.20 — about 20× more.\n"
            "The gap widens as you generate more campaigns and play more runs.\n"
            "\n"
            "  cp .env.example .env   # then fill in ANTHROPIC_API_KEY",
            file=sys.stderr,
        )
        sys.exit(1)

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
    rules = load_rules(RULES_PATH)
    templates = load_templates(TEXT_PATH)
    run = make_run(campaign)
    run.rule_system.set_templates(rules)

    fast_model = (
        args.fast_model
        or os.environ.get("FAST_CORE_MODEL", "gemma3:4b")
    )
    fast_cfg = FastCoreConfig(
        model=fast_model,
        lang=args.lang,
        tone=saga.get("tone") or None,
    )

    # Load T2 cache (arc palette) and T1 cache (node skeletons) if available
    saga_dir = REPO_ROOT / "data" / "nodes" / saga.get("saga_id", "")
    a1_cache_table_path = saga_dir / "a1_cache_table.json"

    if T2_CACHE_PATH.exists():
        run.memory.a2.load_a2_cache_table(T2_CACHE_PATH)
    if a1_cache_table_path.exists():
        run.memory.a2.load_a1_cache_table(a1_cache_table_path)

    # Build M2Classifier if A2 cache is loaded (provides the cached prefix)
    m2_classifier: M2Classifier | None = None
    if run.memory.a2.a2_cache_table:
        import json as _json
        saga_id = saga.get("saga_id", "")
        campaigns_dir = REPO_ROOT / "data" / "campaigns"
        toll_lexicon_path = campaigns_dir / f"{saga_id}_toll_lexicon.json"
        toll_lexicon = _json.loads(toll_lexicon_path.read_text(encoding="utf-8")) if toll_lexicon_path.exists() else []
        toll_lexicon_json = _json.dumps(toll_lexicon, ensure_ascii=False) if toll_lexicon else ""
        rules_json = _json.dumps({"rules": [dataclasses.asdict(r) for r in rules]}, ensure_ascii=False)
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

    current_node_id = saga["start_waypoint_id"]

    # Prefetch the start node while the player reads the intro.
    # The main loop only prefetches next_nodes, so without this the first
    # LLM-mode node would always have empty encounters.
    _prefetch_targets(
        prefetch=prefetch,
        campaign=saga,
        target_ids=[current_node_id],
        run=run,
    )

    render_run_intro(saga)
    pause("Press Enter to step onto the road...")
    nodes_played = 0
    try:
        while current_node_id:
            saga_waypoint = saga["waypoints"][current_node_id]

            # Determine next nodes now so we can trigger prefetch for all of them
            next_nodes = saga_waypoint.get("next_waypoints", [])

            # Trigger background generation for each candidate next node
            if next_nodes:
                _prefetch_targets(
                    prefetch=prefetch,
                    campaign=saga,
                    target_ids=next_nodes,
                    run=run,
                )

            completed_node_memory = _play_node(
                run,
                campaign,
                saga_waypoint,
                rules,
                templates,
                prefetch=prefetch,
                saga_waypoint_id=current_node_id,
            )
            nodes_played += 1

            if next_nodes:
                lookahead_targets = _collect_lookahead_targets(saga, next_nodes)
                _prefetch_targets(
                    prefetch=prefetch,
                    campaign=saga,
                    target_ids=lookahead_targets,
                    run=run,
                    current_waypoint_memory=completed_node_memory,
                )

            if not next_nodes:
                break
            if args.nodes is not None and nodes_played >= args.nodes:
                break

            render_map_hud(run, saga, next_nodes)
            render_input_panel("Choose your next destination")
            next_index = choose_index("> ", len(next_nodes))
            current_node_id = next_nodes[next_index]

            # Trigger Opus for arb 0 of the chosen next node.
            # Runs in background while the player reads the node header + waits for gemma3.
            quasi = build_classifier_input(run.core_state, run.memory, list(run.waypoint_history))
            prefetch.update_arc_state(quasi, current_node_id, 0)

    except KeyboardInterrupt:
        print("\n\nRun interrupted.")
        return
    except (AssetValidationError, ValueError) as exc:
        print(f"\n\nAsset error: {exc}")
        return

    render_run_complete(run)


if __name__ == "__main__":
    main()
