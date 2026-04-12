"""Interactive CLI loop for playing a small Black Archive campaign."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.core.authoring import load_rules, load_templates
from src.core.deterministic_kernel import ArbitrationResult
from src.core.enforcement import apply_option_effects, enforce_rule
from src.core.memory import append_node_event, record_choice, update_after_node
from src.core.narration import render_narration
from src.core.presentation import (
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
from src.core.rule_engine import build_selection_trace, evaluate_rules, select_rule
from src.core.runtime.campaign import (
    REPO_ROOT,
    choose_index,
    make_run,
    resolve_asset_path,
    sync_arbitration_resources,
)
from src.core.signal_interpretation import build_signals, score_themes
from src.core.state_adapter import load_json_asset


DEFAULT_CAMPAIGN = REPO_ROOT / "data" / "campaigns" / "act1_campaign.json"
RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.small.json"
TEXT_PATH = REPO_ROOT / "data" / "text" / "narration_templates.json"


def _play_arbitration(run, node, payload: dict[str, object], templates: dict[str, list[str]], rules) -> None:
    arbitration = node.load_current_arbitration(payload)
    sync_arbitration_resources(run, arbitration)
    append_node_event(
        node.memory,
        "arbitration_loaded",
        arbitration_id=arbitration.arbitration_id,
        scene_type=arbitration.context.scene_type,
        context_id=arbitration.context.context_id,
    )

    signals = build_signals(arbitration)
    theme_scores = score_themes(arbitration, signals)
    evaluations = evaluate_rules(arbitration, rules, theme_scores)
    node.rule_state.reset_for_arbitration()
    node.rule_state.record_evaluations(evaluations)
    selected = select_rule(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    node.rule_state.record_selected_rule(selected.rule.id if selected else None)
    node.rule_state.record_selection_trace(
        build_selection_trace(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    )
    run.rule_system.record_selected_rule(selected.rule.id if selected else None)
    append_node_event(
        node.memory,
        "rule_selected",
        arbitration_id=arbitration.arbitration_id,
        selected_rule_id=selected.rule.id if selected else None,
        matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
    )

    option_results, sanity_delta = enforce_rule(arbitration, selected.rule if selected else None)
    narration = render_narration(
        arbitration=arbitration,
        rule=selected.rule if selected else None,
        templates=templates,
        enabled=True,
    )

    render_arbitration_view(run, arbitration, selected.rule if selected else None)
    render_choices(option_results)
    render_input_panel("Choose an option")

    choice_index = choose_index("> ", len(option_results))
    chosen_result = option_results[choice_index]
    arbitration.select_option(chosen_result.option_id)
    selected_option = arbitration.get_option(chosen_result.option_id) or {}

    record_choice(
        node.memory,
        arbitration=arbitration,
        selected_rule_id=selected.rule.id if selected else None,
        selected_rule_theme=selected.rule.theme if selected else None,
        selected_result=chosen_result,
    )
    append_node_event(
        node.memory,
        "option_chosen",
        arbitration_id=arbitration.arbitration_id,
        option_id=chosen_result.option_id,
        verdict=chosen_result.verdict,
        sanity_delta=chosen_result.sanity_cost,
    )

    applied_notes = apply_option_effects(run, selected_option, chosen_result)
    arbitration.set_result(
        ArbitrationResult(
            selected_rule_id=selected.rule.id if selected else None,
            matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
            option_results=option_results,
            sanity_delta=sanity_delta,
            theme_scores=theme_scores,
            narration=narration,
        )
    )
    arbitration.mark_applied()
    node.close_current_arbitration()
    append_node_event(
        node.memory,
        "arbitration_finalized",
        arbitration_id=arbitration.arbitration_id,
        selected_rule_id=selected.rule.id if selected else None,
        player_choice=chosen_result.option_id,
    )

    render_result(run, chosen_result, narration, applied_notes)
    pause()


def _play_node(run, campaign_node: dict[str, object], rules, templates: dict[str, list[str]]) -> None:
    node_spec = load_json_asset(resolve_asset_path(campaign_node["node_file"]))
    run.floor = node_spec["floor"]
    run.core_state.floor = node_spec["floor"]
    run.core_state.scene_type = node_spec["node_type"]

    node = run.start_node(node_id=node_spec["node_id"], node_type=node_spec["node_type"], floor=node_spec["floor"])
    append_node_event(node.memory, "node_entered", node_id=node.node_id, node_type=node.node_type, floor=node.floor)

    render_node_header(run, campaign_node)

    for arbitration_spec in node_spec.get("arbitrations", []):
        payload = load_json_asset(resolve_asset_path(arbitration_spec["file"]))
        _play_arbitration(run, node, payload, templates, rules)

    node.memory.node_summary = f"{node.node_type}:{len(node.memory.choices_made)}_arbitrations:sanity={node.memory.sanity_lost_in_node}"
    append_node_event(
        node.memory,
        "node_finalized",
        node_id=node.node_id,
        arbitration_count=len(node.memory.choices_made),
        sanity_lost=node.memory.sanity_lost_in_node,
    )
    update_after_node(run.memory, node.memory)
    summary = node.build_summary(sanity_delta=node.memory.sanity_lost_in_node)
    run.close_current_node(summary=summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Play a small Black Archive CLI campaign.")
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN, help="Path to a campaign JSON file.")
    args = parser.parse_args()

    campaign = load_json_asset(args.campaign)
    rules = load_rules(RULES_PATH)
    templates = load_templates(TEXT_PATH)
    run = make_run(campaign)
    run.rule_system.set_templates(rules)

    render_run_intro(campaign)
    pause("Press Enter to step onto the road...")

    current_node_id = campaign["start_node_id"]
    try:
        while current_node_id:
            campaign_node = campaign["nodes"][current_node_id]
            _play_node(run, campaign_node, rules, templates)

            next_nodes = campaign_node.get("next_nodes", [])
            if not next_nodes:
                break

            render_map_hud(run, campaign, next_nodes)
            render_input_panel("Choose your next destination")
            next_index = choose_index("> ", len(next_nodes))
            current_node_id = next_nodes[next_index]

    except KeyboardInterrupt:
        print("\n\nRun interrupted.")
        return

    render_run_complete(run)


if __name__ == "__main__":
    main()
