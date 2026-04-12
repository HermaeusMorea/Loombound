from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.authoring import load_rules, load_templates
from src.core.deterministic_kernel import (
    CoreStateView,
    MetaStateView,
    ArbitrationResult,
    Run,
    RunSnapshot,
)
from src.core.enforcement import enforce_rule
from src.core.narration import render_narration
from src.core.rule_engine import evaluate_rules, select_rule
from src.core.signal_interpretation import build_signals, score_themes
from src.core.state_adapter import load_json_asset


# runtime/cli.py now lives under src/core/runtime/, so we walk back to the
# repository root before resolving data files.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONTEXT = REPO_ROOT / "data" / "sample_contexts" / "map" / "map_01.json"
RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.small.json"
TEXT_PATH = REPO_ROOT / "data" / "text" / "narration_templates.json"


def main() -> None:
    # This CLI now demonstrates the intended runtime shape:
    # Run -> Node -> Arbitration -> judgement pipeline.
    parser = argparse.ArgumentParser(description="Run the li-director-sts2 offline demo.")
    parser.add_argument("--context", type=Path, default=DEFAULT_CONTEXT, help="Path to an arbitration JSON file.")
    parser.add_argument("--no-narration", action="store_true", help="Disable narration output.")
    args = parser.parse_args()

    payload = load_json_asset(args.context)
    context_payload = payload.get("context", payload)
    scene_type = context_payload.get("scene_type", context_payload.get("decision_type", "unknown"))
    floor = context_payload["floor"]
    act = context_payload.get("act", 1)
    resources = context_payload.get("resources", {})
    run = Run(
        run_id=f"offline_run:{args.context.stem}",
        act=act,
        floor=floor,
        core_state=CoreStateView(
            floor=floor,
            act=act,
            gold=resources.get("gold"),
            scene_type=scene_type,
            metadata={"hp_ratio": resources.get("hp_ratio")},
        ),
        meta_state=MetaStateView(),
    )
    node = run.start_node(
        node_id=f"{scene_type}:{context_payload['context_id']}",
        node_type=scene_type,
        floor=floor,
    )
    arbitration = node.load_current_arbitration(payload)

    rules = load_rules(RULES_PATH)
    templates = load_templates(TEXT_PATH)

    # Pipeline:
    # Run -> Node -> Arbitration -> signals -> theme scores -> rule evaluations
    # -> selected rule -> enforcement -> optional narration -> snapshot
    signals = build_signals(arbitration)
    theme_scores = score_themes(arbitration, signals)
    evaluations = evaluate_rules(arbitration, rules, theme_scores)
    selected = select_rule(evaluations)
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
    # Emit a structured JSON result so runs are easy to inspect, diff, and
    # eventually replay.
    print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
