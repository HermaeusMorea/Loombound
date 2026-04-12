"""Read-only observation demo that exports native-like input into arbitration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.authoring import load_rules, load_templates
from src.core.deterministic_kernel import (
    ArbitrationResult,
    CoreStateView,
    MetaStateView,
    RunSnapshot,
)
from src.core.enforcement import enforce_rule
from src.core.narration import render_narration
from src.core.overlay_integration import ObservedScene, observed_scene_to_arbitration_payload
from src.core.rule_engine import build_selection_trace, evaluate_rules, select_rule
from src.core.runtime import Run
from src.core.signal_interpretation import build_signals, score_themes
from src.core.state_adapter import load_json_asset


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OBSERVATION = REPO_ROOT / "data" / "native_observations" / "shop_observed_01.json"
RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.small.json"
TEXT_PATH = REPO_ROOT / "data" / "text" / "narration_templates.json"


def main() -> None:
    """Observe a read-only scene, export it, and judge it offline."""

    parser = argparse.ArgumentParser(
        description="Run a read-only observation adapter demo and inspect the exported Arbitration."
    )
    parser.add_argument(
        "--observation",
        type=Path,
        default=DEFAULT_OBSERVATION,
        help="Path to a read-only observed scene JSON file.",
    )
    parser.add_argument("--no-narration", action="store_true", help="Disable narration output.")
    args = parser.parse_args()

    observed_scene = ObservedScene.from_dict(load_json_asset(args.observation))
    arbitration_payload = observed_scene_to_arbitration_payload(observed_scene)
    rules = load_rules(RULES_PATH)
    templates = load_templates(TEXT_PATH)
    context_payload = arbitration_payload["context"]

    run = Run(
        run_id=f"observed_run:{args.observation.stem}",
        act=observed_scene.act,
        floor=observed_scene.floor,
        core_state=CoreStateView(
            floor=observed_scene.floor,
            act=observed_scene.act,
            gold=observed_scene.resources.get("gold"),
            scene_type=observed_scene.scene_type,
            metadata={"hp_ratio": observed_scene.resources.get("hp_ratio")},
        ),
        meta_state=MetaStateView(),
    )
    run.rule_system.set_templates(rules)
    node = run.start_node(
        node_id=f"{observed_scene.scene_type}:{observed_scene.observation_id}",
        node_type=observed_scene.scene_type,
        floor=observed_scene.floor,
    )
    arbitration = node.load_current_arbitration(arbitration_payload)

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
    option_results, collapse_delta = enforce_rule(arbitration, selected.rule if selected else None)
    narration = render_narration(
        arbitration=arbitration,
        rule=selected.rule if selected else None,
        templates=templates,
        enabled=not args.no_narration,
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
    run.close_current_node(summary=node.build_summary(collapse_delta=collapse_delta))

    snapshot = RunSnapshot(
        arbitration_id=arbitration.arbitration_id,
        selected_rule_id=selected.rule.id if selected else None,
        matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
        theme_scores=theme_scores,
        option_results=option_results,
        ritual_collapse_delta=collapse_delta,
        narration=narration,
    )
    print(
        json.dumps(
            {
                "observed_scene": {
                    "observation_id": observed_scene.observation_id,
                    "scene_type": observed_scene.scene_type,
                    "floor": observed_scene.floor,
                    "act": observed_scene.act,
                    "event_trace": observed_scene.event_trace,
                },
                "exported_arbitration": arbitration_payload,
                "snapshot": snapshot.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
