from __future__ import annotations

from src.core.models import ChoiceContext, OptionResult, RuleTemplate


def enforce_rule(context: ChoiceContext, rule: RuleTemplate | None) -> tuple[list[OptionResult], int]:
    if rule is None:
        return (
            [
                OptionResult(
                    option_id=option.option_id,
                    label=option.label,
                    verdict="keep_ritual",
                    reasons=["no_rule_selected"],
                    collapse_if_taken=0,
                )
                for option in context.options
            ],
            0,
        )

    results: list[OptionResult] = []
    collapse_delta = 0
    preferred_tags = set(rule.preferred_option_tags)
    forbidden_tags = set(rule.forbidden_option_tags)

    for option in context.options:
        option_tags = set(option.tags)
        reasons: list[str] = []
        verdict = "keep_ritual"
        option_penalty = 0

        if forbidden_tags & option_tags:
            verdict = "break_ritual"
            reasons.append(f"contains_forbidden_tags:{','.join(sorted(forbidden_tags & option_tags))}")
            option_penalty = rule.collapse_penalty
        elif preferred_tags and preferred_tags & option_tags:
            reasons.append(f"contains_preferred_tags:{','.join(sorted(preferred_tags & option_tags))}")
        elif preferred_tags:
            verdict = "break_ritual"
            reasons.append("missing_preferred_tags")
            option_penalty = rule.collapse_penalty
        else:
            reasons.append("rule_allows_option")

        collapse_delta = max(collapse_delta, option_penalty)
        results.append(
            OptionResult(
                option_id=option.option_id,
                label=option.label,
                verdict=verdict,
                reasons=reasons,
                collapse_if_taken=option_penalty,
            )
        )

    return results, collapse_delta


# TODO: Split "soft warning" and "future hard lock" into separate enforcement stages.

