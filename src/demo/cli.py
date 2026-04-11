from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.enforcement import enforce_rule
from src.core.models import ChoiceContext, RuleTemplate, RunSnapshot
from src.core.narrator import render_narration
from src.core.rule_matcher import evaluate_rules
from src.core.rule_selector import select_rule
from src.core.signals import build_signals
from src.core.theme_scorer import score_themes


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTEXT = REPO_ROOT / "data" / "sample_contexts" / "map" / "map_01.json"
RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.small.json"
TEXT_PATH = REPO_ROOT / "data" / "text" / "narration_templates.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rules(path: Path) -> list[RuleTemplate]:
    payload = load_json(path)
    return [RuleTemplate.from_dict(item) for item in payload["rules"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the li-director-sts2 offline demo.")
    parser.add_argument("--context", type=Path, default=DEFAULT_CONTEXT, help="Path to a choice context JSON file.")
    parser.add_argument("--no-narration", action="store_true", help="Disable narration output.")
    args = parser.parse_args()

    context = ChoiceContext.from_dict(load_json(args.context))
    rules = load_rules(RULES_PATH)
    templates = load_json(TEXT_PATH)

    signals = build_signals(context)
    theme_scores = score_themes(context, signals)
    evaluations = evaluate_rules(context, rules, theme_scores)
    selected = select_rule(evaluations)
    option_results, collapse_delta = enforce_rule(context, selected.rule if selected else None)
    narration = render_narration(
        context=context,
        rule=selected.rule if selected else None,
        templates=templates,
        enabled=not args.no_narration,
    )

    snapshot = RunSnapshot(
        context_id=context.context_id,
        selected_rule_id=selected.rule.id if selected else None,
        matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
        theme_scores=theme_scores,
        option_results=option_results,
        ritual_collapse_delta=collapse_delta,
        narration=narration,
    )
    print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

