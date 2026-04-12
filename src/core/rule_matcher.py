from __future__ import annotations

from src.core.models import ChoiceContext, RuleEvaluation, RuleTemplate


def evaluate_rule(
    context: ChoiceContext,
    rule: RuleTemplate,
    theme_scores: dict[str, float],
) -> RuleEvaluation:
    # Evaluate one rule in isolation so we can keep both the boolean result and
    # the explanation of why it matched or failed.
    reasons: list[str] = []

    if context.decision_type not in rule.decision_types:
        return RuleEvaluation(rule=rule, matched=False, reasons=["decision_type_mismatch"], theme_score=0.0)

    if rule.match.required_context_tags:
        # Context tags act as coarse scene markers, e.g. "route_choice" or
        # "temptation". They let rules say "I only belong in this sort of room".
        missing_tags = [tag for tag in rule.match.required_context_tags if tag not in context.tags]
        if missing_tags:
            return RuleEvaluation(
                rule=rule,
                matched=False,
                reasons=[f"missing_context_tags:{','.join(missing_tags)}"],
                theme_score=0.0,
            )
        reasons.append("context_tags_matched")

    hp_ratio = float(context.resources.get("hp_ratio", 1.0))
    gold = int(context.resources.get("gold", 0))

    # Numeric bounds are the first prototype's main trigger language.
    if rule.match.min_hp_ratio is not None and hp_ratio < rule.match.min_hp_ratio:
        return RuleEvaluation(rule=rule, matched=False, reasons=["hp_below_min"], theme_score=0.0)
    if rule.match.max_hp_ratio is not None and hp_ratio > rule.match.max_hp_ratio:
        return RuleEvaluation(rule=rule, matched=False, reasons=["hp_above_max"], theme_score=0.0)
    if rule.match.min_gold is not None and gold < rule.match.min_gold:
        return RuleEvaluation(rule=rule, matched=False, reasons=["gold_below_min"], theme_score=0.0)
    if rule.match.max_gold is not None and gold > rule.match.max_gold:
        return RuleEvaluation(rule=rule, matched=False, reasons=["gold_above_max"], theme_score=0.0)

    reasons.append("numeric_bounds_matched")
    return RuleEvaluation(
        rule=rule,
        matched=True,
        reasons=reasons,
        theme_score=theme_scores.get(rule.theme, 0.0),
    )


def evaluate_rules(
    context: ChoiceContext,
    rules: list[RuleTemplate],
    theme_scores: dict[str, float],
) -> list[RuleEvaluation]:
    # Keep evaluation and selection separate: first ask "what is eligible?",
    # then ask "which eligible rule should win?"
    return [evaluate_rule(context=context, rule=rule, theme_scores=theme_scores) for rule in rules]


# TODO: Support explicit exception clauses and conflict metadata on rules.
