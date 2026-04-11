from __future__ import annotations

from src.core.models import RuleEvaluation


def select_rule(evaluations: list[RuleEvaluation]) -> RuleEvaluation | None:
    matched = [item for item in evaluations if item.matched]
    if not matched:
        return None

    return sorted(
        matched,
        key=lambda item: (-item.theme_score, -item.rule.priority, item.rule.id),
    )[0]


# TODO: Revisit tie-breaking once multiple simultaneously active rules are allowed.

