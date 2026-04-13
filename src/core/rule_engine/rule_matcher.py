"""Evaluate which rule templates are eligible for one arbitration."""

from __future__ import annotations

from src.core.deterministic_kernel import RuleEvaluation, RuleTemplate
from src.core.runtime import Arbitration


def evaluate_rule(
    arbitration: Arbitration,
    rule: RuleTemplate,
    theme_scores: dict[str, float],
) -> RuleEvaluation:
    # Evaluate one rule in isolation so we can keep both the boolean result and
    # the explanation of why it matched or failed.
    reasons: list[str] = []

    if arbitration.context.scene_type not in rule.decision_types:
        return RuleEvaluation(rule=rule, matched=False, reasons=["decision_type_mismatch"], theme_score=0.0)

    if rule.required_context_tags:
        # Context tags act as coarse scene markers, e.g. "branching_path" or
        # "temptation". They let rules say "I only belong in this sort of room".
        missing_tags = [tag for tag in rule.required_context_tags if tag not in arbitration.context.tags]
        if missing_tags:
            return RuleEvaluation(
                rule=rule,
                matched=False,
                reasons=[f"missing_context_tags:{','.join(missing_tags)}"],
                theme_score=0.0,
            )
        reasons.append("context_tags_matched")

    health = int(arbitration.context.resources.get("health") or 0)
    money = int(arbitration.context.resources.get("money") or 0)
    sanity = int(arbitration.context.resources.get("sanity") or 0)

    # Numeric bounds are the first prototype's main trigger language.
    if rule.min_health is not None and health < rule.min_health:
        return RuleEvaluation(rule=rule, matched=False, reasons=["health_below_min"], theme_score=0.0)
    if rule.max_health is not None and health > rule.max_health:
        return RuleEvaluation(rule=rule, matched=False, reasons=["health_above_max"], theme_score=0.0)
    if rule.min_money is not None and money < rule.min_money:
        return RuleEvaluation(rule=rule, matched=False, reasons=["money_below_min"], theme_score=0.0)
    if rule.max_money is not None and money > rule.max_money:
        return RuleEvaluation(rule=rule, matched=False, reasons=["money_above_max"], theme_score=0.0)
    if rule.min_sanity is not None and sanity < rule.min_sanity:
        return RuleEvaluation(rule=rule, matched=False, reasons=["sanity_below_min"], theme_score=0.0)
    if rule.max_sanity is not None and sanity > rule.max_sanity:
        return RuleEvaluation(rule=rule, matched=False, reasons=["sanity_above_max"], theme_score=0.0)

    reasons.append("numeric_bounds_matched")
    return RuleEvaluation(
        rule=rule,
        matched=True,
        reasons=reasons,
        theme_score=theme_scores.get(rule.theme, 0.0),
    )


def evaluate_rules(
    arbitration: Arbitration,
    rules: list[RuleTemplate],
    theme_scores: dict[str, float],
) -> list[RuleEvaluation]:
    # Keep evaluation and selection separate: first ask "what is eligible?",
    # then ask "which eligible rule should win?"
    return [evaluate_rule(arbitration=arbitration, rule=rule, theme_scores=theme_scores) for rule in rules]


# TODO: Support explicit exception clauses and conflict metadata on rules.
