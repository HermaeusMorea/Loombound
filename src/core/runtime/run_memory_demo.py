"""Run-level demo that exercises nodes, arbitrations, and memory updates."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.core.authoring import load_rules, load_templates
from src.core.deterministic_kernel import (
    ArbitrationResult,
    CoreStateView,
    MetaStateView,
    OptionResult,
    RunSnapshot,
)
from src.core.enforcement import enforce_rule
from src.core.memory import NodeChoiceRecord, NodeEvent, ViolationRecord, run_memory_to_dict, update_after_node
from src.core.narration import render_narration
from src.core.rule_engine import build_selection_trace, evaluate_rules, select_rule
from src.core.runtime import Run
from src.core.signal_interpretation import build_signals, score_themes
from src.core.state_adapter import load_json_asset


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_NODES = [
    REPO_ROOT / "data" / "sample_nodes" / "combat_rewards_01.json",
    REPO_ROOT / "data" / "sample_nodes" / "shop_01.json",
    REPO_ROOT / "data" / "sample_nodes" / "event_01.json",
]
RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.small.json"
TEXT_PATH = REPO_ROOT / "data" / "text" / "narration_templates.json"


def _pick_default_option(option_results: list[OptionResult]) -> str:
    """Prefer the first keep_ritual option when auto-selecting choices."""

    for item in option_results:
        if item.verdict == "keep_ritual":
            return item.option_id
    return option_results[0].option_id


def _choose_option(
    arbitration_id: str,
    option_results: list[OptionResult],
    forced_choice: str | None,
    interactive: bool,
) -> str:
    valid_ids = {item.option_id for item in option_results}
    if forced_choice:
        if forced_choice not in valid_ids:
            raise ValueError(f"Unknown option id '{forced_choice}' for arbitration '{arbitration_id}'.")
        return forced_choice

    if not interactive:
        return _pick_default_option(option_results)

    print(f"\n[{arbitration_id}] Pick an option:")
    for item in option_results:
        print(f"- {item.option_id}: {item.label} [{item.verdict}]")

    default_choice = _pick_default_option(option_results)
    while True:
        raw = input(f"choice [{default_choice}]: ").strip()
        choice = raw or default_choice
        if choice in valid_ids:
            return choice
        print("Unknown option id, try again.")


def _build_local_flags(selected_result: OptionResult) -> list[str]:
    flags: list[str] = []
    if selected_result.verdict == "break_ritual":
        flags.append("violated_active_rule")
    reason_blob = " ".join(selected_result.reasons)
    if "greedy" in reason_blob or "luxury" in reason_blob:
        flags.append("chose_greedy_option")
    if "safe" in reason_blob:
        flags.append("chose_safe_option")
    return flags


def _resolve_asset_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _load_node_specs(node_paths: list[Path]) -> list[dict[str, Any]]:
    """Load authored node scripts from disk."""

    return [load_json_asset(path) for path in node_paths]


def _load_context_specs(context_paths: list[Path]) -> list[dict[str, Any]]:
    """Wrap legacy one-arbitration payloads into one-arbitration node specs."""

    specs: list[dict[str, Any]] = []
    for path in context_paths:
        payload = load_json_asset(path)
        context = payload.get("context", payload)
        node_type = context.get("scene_type", context.get("decision_type", "unknown"))
        specs.append(
            {
                "node_id": f"{node_type}:{context['context_id']}",
                "node_type": node_type,
                "floor": context["floor"],
                "arbitrations": [{"file": str(path.relative_to(REPO_ROOT)) if path.is_absolute() else str(path)}],
            }
        )
    return specs


def _record_arbitration_into_node_memory(
    node_memory: Any,
    *,
    context_id: str,
    scene_type: str,
    selected_rule_id: str | None,
    selected_rule_theme: str | None,
    selected_result: OptionResult,
) -> None:
    """Promote one finished arbitration outcome into the current NodeMemory."""

    local_flags = _build_local_flags(selected_result)
    node_memory.choices_made.append(
        NodeChoiceRecord(
            context_id=context_id,
            scene_type=scene_type,
            active_rule_id=selected_rule_id,
            active_rule_theme=selected_rule_theme,
            player_choice=selected_result.option_id,
            violation_triggered=selected_result.verdict == "break_ritual",
            collapse_delta=selected_result.collapse_if_taken,
            local_flags=local_flags,
        )
    )

    if selected_result.verdict == "break_ritual":
        node_memory.violations_in_node.append(
            ViolationRecord(
                context_id=context_id,
                rule_id=selected_rule_id,
                scene_type=scene_type,
                option_id=selected_result.option_id,
                flags=local_flags.copy(),
                collapse_delta=selected_result.collapse_if_taken,
            )
        )

    node_memory.collapse_gained_in_node += selected_result.collapse_if_taken
    for flag in local_flags:
        if flag not in node_memory.important_flags:
            node_memory.important_flags.append(flag)


def _append_node_event(node_memory: Any, event_type: str, **payload: Any) -> None:
    """Record one structured lifecycle event inside the current node."""

    node_memory.events.append(NodeEvent(event_type=event_type, payload=payload))


def _build_run() -> Run:
    """Create a minimal deterministic run shell for the offline demo."""

    return Run(
        run_id="offline_memory_demo",
        act=1,
        floor=1,
        core_state=CoreStateView(floor=1, act=1),
        meta_state=MetaStateView(),
    )


def main() -> None:
    """Run an offline node lifecycle demo with persistent RunMemory."""

    parser = argparse.ArgumentParser(
        description="Run a node-lifecycle offline demo with persistent RunMemory and per-node NodeMemory."
    )
    parser.add_argument(
        "--node",
        type=Path,
        action="append",
        dest="nodes",
        help="Path to a node script JSON file. Repeat to process multiple nodes in order.",
    )
    parser.add_argument(
        "--context",
        type=Path,
        action="append",
        dest="contexts",
        help="Legacy path to a single arbitration JSON file. Each context becomes a one-arbitration node.",
    )
    parser.add_argument(
        "--choice",
        action="append",
        dest="choices",
        help="Forced option id for each arbitration in traversal order.",
    )
    parser.add_argument("--no-narration", action="store_true", help="Disable narration output.")
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Do not prompt for option ids. If no --choice is provided, auto-pick the first keep_ritual option.",
    )
    args = parser.parse_args()

    if args.nodes:
        node_specs = _load_node_specs(args.nodes)
    elif args.contexts:
        node_specs = _load_context_specs(args.contexts)
    else:
        node_specs = _load_node_specs(DEFAULT_NODES)

    rules = load_rules(RULES_PATH)
    templates = load_templates(TEXT_PATH)
    run = _build_run()
    run.rule_system.set_templates(rules)
    forced_choices = args.choices or []
    choice_cursor = 0
    history: list[dict[str, Any]] = []

    for node_spec in node_specs:
        node_type = node_spec["node_type"]
        floor = node_spec["floor"]

        run.floor = floor
        run.core_state.floor = floor
        run.core_state.scene_type = node_type

        node = run.start_node(
            node_id=node_spec["node_id"],
            node_type=node_type,
            floor=floor,
        )
        _append_node_event(
            node.memory,
            "node_entered",
            node_id=node.node_id,
            node_type=node.node_type,
            floor=node.floor,
        )

        arbitration_history: list[dict[str, Any]] = []
        arbitration_specs = node_spec.get("arbitrations", [])
        for arbitration_spec in arbitration_specs:
            arbitration_path = _resolve_asset_path(arbitration_spec["file"])
            payload = load_json_asset(arbitration_path)
            arbitration = node.load_current_arbitration(payload)
            _append_node_event(
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
            selected = select_rule(
                evaluations,
                rule_system=run.rule_system,
                run_memory=run.memory,
            )
            node.rule_state.record_selected_rule(selected.rule.id if selected else None)
            node.rule_state.record_selection_trace(
                build_selection_trace(
                    evaluations,
                    rule_system=run.rule_system,
                    run_memory=run.memory,
                )
            )
            run.rule_system.record_selected_rule(selected.rule.id if selected else None)
            _append_node_event(
                node.memory,
                "rule_selected",
                arbitration_id=arbitration.arbitration_id,
                selected_rule_id=selected.rule.id if selected else None,
                matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
            )
            option_results, collapse_delta = enforce_rule(arbitration, selected.rule if selected else None)
            narration = render_narration(
                arbitration=arbitration,
                rule=selected.rule if selected else None,
                templates=templates,
                enabled=not args.no_narration,
            )

            forced_choice = forced_choices[choice_cursor] if choice_cursor < len(forced_choices) else None
            chosen_option_id = _choose_option(
                arbitration_id=arbitration.arbitration_id,
                option_results=option_results,
                forced_choice=forced_choice,
                interactive=not args.no_input,
            )
            choice_cursor += 1

            arbitration.select_option(chosen_option_id)
            selected_result = next(item for item in option_results if item.option_id == chosen_option_id)
            _record_arbitration_into_node_memory(
                node.memory,
                context_id=arbitration.context.context_id,
                scene_type=arbitration.context.scene_type,
                selected_rule_id=selected.rule.id if selected else None,
                selected_rule_theme=selected.rule.theme if selected else None,
                selected_result=selected_result,
            )
            _append_node_event(
                node.memory,
                "option_chosen",
                arbitration_id=arbitration.arbitration_id,
                option_id=chosen_option_id,
                verdict=selected_result.verdict,
                collapse_delta=selected_result.collapse_if_taken,
            )

            arbitration.set_result(
                ArbitrationResult(
                    selected_rule_id=selected.rule.id if selected else None,
                    matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
                    option_results=option_results,
                    ritual_collapse_delta=collapse_delta,
                    theme_scores=theme_scores,
                    narration=narration,
                )
            )
            arbitration.mark_applied()
            node.close_current_arbitration()
            _append_node_event(
                node.memory,
                "arbitration_finalized",
                arbitration_id=arbitration.arbitration_id,
                selected_rule_id=selected.rule.id if selected else None,
                player_choice=chosen_option_id,
            )

            snapshot = RunSnapshot(
                arbitration_id=arbitration.arbitration_id,
                selected_rule_id=selected.rule.id if selected else None,
                matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
                theme_scores=theme_scores,
                option_results=option_results,
                ritual_collapse_delta=collapse_delta,
                narration=narration,
            )
            arbitration_history.append(
                {
                    "snapshot": snapshot.to_dict(),
                    "player_choice": chosen_option_id,
                }
            )

        node.memory.node_summary = (
            f"{node.node_type}:{len(node.memory.choices_made)}_arbitrations:"
            f"collapse={node.memory.collapse_gained_in_node}"
        )
        _append_node_event(
            node.memory,
            "node_finalized",
            node_id=node.node_id,
            arbitration_count=len(node.memory.choices_made),
            collapse_gained=node.memory.collapse_gained_in_node,
        )
        node_summary = node.build_summary(
            collapse_delta=node.memory.collapse_gained_in_node,
            important_flags=node.memory.important_flags,
        )
        update_after_node(run.memory, node.memory)
        run.close_current_node(summary=node_summary)

        history.append(
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "floor": node.floor,
                "arbitrations": arbitration_history,
                "node_memory": asdict(node.memory),
                "node_summary": asdict(node_summary),
                "node_rule_state": {
                    "available_rule_ids": node.rule_state.available_rule_ids,
                    "candidate_rule_ids": node.rule_state.candidate_rule_ids,
                    "selected_rule_id": node.rule_state.selected_rule_id,
                    "selection_trace": node.rule_state.selection_trace,
                },
                "run_memory_after_node": run_memory_to_dict(run.memory),
                "run_rule_system_after_node": {
                    "recently_used_rule_ids": list(run.rule_system.recently_used_rule_ids),
                    "rule_use_counts": dict(run.rule_system.rule_use_counts),
                },
            }
        )

    print(
        json.dumps(
            {
                "processed_nodes": [item["node_id"] for item in history],
                "history": history,
                "final_run_memory": run_memory_to_dict(run.memory),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
