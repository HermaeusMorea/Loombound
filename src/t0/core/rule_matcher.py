"""Evaluate which rule templates are eligible for one encounter."""

from __future__ import annotations

from src.t0.memory import RuleEvaluation, RuleTemplate
from src.t0.memory import Encounter


def evaluate_rule(
    encounter: Encounter,
    rule: RuleTemplate,
) -> RuleEvaluation:
    reasons: list[str] = []

    if encounter.context.scene_type not in rule.decision_types:
        return RuleEvaluation(rule=rule, matched=False, reasons=["decision_type_mismatch"])

    if rule.required_context_tags:
        missing_tags = [tag for tag in rule.required_context_tags if tag not in encounter.context.tags]
        if missing_tags:
            return RuleEvaluation(
                rule=rule,
                matched=False,
                reasons=[f"missing_context_tags:{','.join(missing_tags)}"],
            )
        reasons.append("context_tags_matched")

    health = int(encounter.context.resources.get("health") or 0)
    money = int(encounter.context.resources.get("money") or 0)
    sanity = int(encounter.context.resources.get("sanity") or 0)

    if rule.min_health is not None and health < rule.min_health:
        return RuleEvaluation(rule=rule, matched=False, reasons=["health_below_min"])
    if rule.max_health is not None and health > rule.max_health:
        return RuleEvaluation(rule=rule, matched=False, reasons=["health_above_max"])
    if rule.min_money is not None and money < rule.min_money:
        return RuleEvaluation(rule=rule, matched=False, reasons=["money_below_min"])
    if rule.max_money is not None and money > rule.max_money:
        return RuleEvaluation(rule=rule, matched=False, reasons=["money_above_max"])
    if rule.min_sanity is not None and sanity < rule.min_sanity:
        return RuleEvaluation(rule=rule, matched=False, reasons=["sanity_below_min"])
    if rule.max_sanity is not None and sanity > rule.max_sanity:
        return RuleEvaluation(rule=rule, matched=False, reasons=["sanity_above_max"])

    reasons.append("numeric_bounds_matched")
    return RuleEvaluation(rule=rule, matched=True, reasons=reasons)


def evaluate_rules(
    encounter: Encounter,
    rules: list[RuleTemplate],
) -> list[RuleEvaluation]:
    return [evaluate_rule(encounter=encounter, rule=rule) for rule in rules]


# TODO: Support explicit exception clauses and conflict metadata on rules.
