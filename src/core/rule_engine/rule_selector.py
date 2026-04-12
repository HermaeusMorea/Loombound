from __future__ import annotations

from src.core.deterministic_kernel import RuleEvaluation


def select_rule(evaluations: list[RuleEvaluation]) -> RuleEvaluation | None:
    # The prototype allows at most one active rule per decision node.
    matched = [item for item in evaluations if item.matched]
    if not matched:
        return None

    # Sort order expresses the current policy:
    # 1. higher theme fit
    # 2. higher rule priority
    # 3. stable deterministic tie-break by id
    return sorted(
        matched,
        key=lambda item: (-item.theme_score, -item.rule.priority, item.rule.id),
    )[0]


# TODO: Revisit tie-breaking once multiple simultaneously active rules are allowed.
