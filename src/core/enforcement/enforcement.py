"""Turn a selected rule into per-option sanity verdicts."""

from __future__ import annotations

from src.core.deterministic_kernel import OptionResult, RuleTemplate
from src.core.runtime import Arbitration


def enforce_rule(arbitration: Arbitration, rule: RuleTemplate | None) -> list[OptionResult]:
    # Turn one selected rule into per-option verdicts.
    # This layer does not block actions; it only labels them and computes the
    # soft sanity consequence of taking them.
    if rule is None:
        return [
            OptionResult(
                option_id=option["option_id"],
                label=option["label"],
                verdict="stable",
                reasons=["no_rule_selected"],
                sanity_cost=0,
            )
            for option in arbitration.options
        ]

    results: list[OptionResult] = []
    preferred_tags = set(rule.preferred_option_tags)
    forbidden_tags = set(rule.forbidden_option_tags)

    for option in arbitration.options:
        # Compare each option against the selected rule's preferred / forbidden
        # vocabulary. This is deliberately simple so rule behavior stays easy to
        # reason about in the prototype.
        option_tags = set(option.get("tags", []))
        reasons: list[str] = []
        verdict = "stable"
        option_penalty = 0

        if forbidden_tags & option_tags:
            verdict = "destabilizing"
            reasons.append(f"contains_forbidden_tags:{','.join(sorted(forbidden_tags & option_tags))}")
            option_penalty = rule.sanity_penalty
        elif preferred_tags and preferred_tags & option_tags:
            reasons.append(f"contains_preferred_tags:{','.join(sorted(preferred_tags & option_tags))}")
        elif preferred_tags:
            verdict = "destabilizing"
            reasons.append("missing_preferred_tags")
            option_penalty = rule.sanity_penalty
        else:
            reasons.append("rule_allows_option")

        results.append(
            OptionResult(
                option_id=option["option_id"],
                label=option["label"],
                verdict=verdict,
                reasons=reasons,
                sanity_cost=option_penalty,
            )
        )

    return results


# TODO: Split "soft warning" and "future hard lock" into separate enforcement stages.
