"""Turn a selected rule into per-option sanity verdicts."""

from __future__ import annotations

from src.core.deterministic_kernel import OptionResult, RuleTemplate
from src.core.runtime import Arbitration


def enforce_rule(arbitration: Arbitration, rule: RuleTemplate | None) -> list[OptionResult]:
    # Apply M2-assigned verdict to each option. sanity_penalty comes from the
    # selected rule (if any); non-stable verdict always incurs the penalty.
    results: list[OptionResult] = []
    for option in arbitration.options:
        m2_verdict = option.get("verdict", "")
        verdict = m2_verdict if m2_verdict else "stable"
        penalty = (rule.sanity_penalty if rule else 1) if verdict != "stable" else 0
        results.append(
            OptionResult(
                option_id=option["option_id"],
                label=option["label"],
                verdict=verdict,
                reasons=[f"m2_verdict:{verdict}" if m2_verdict else "no_m2_verdict"],
                sanity_cost=penalty,
            )
        )
    return results


# TODO: Split "soft warning" and "future hard lock" into separate enforcement stages.
