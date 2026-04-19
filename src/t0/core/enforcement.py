"""Turn a selected rule into per-option toll outcomes."""

from __future__ import annotations

from src.t0.memory import OptionResult, RuleTemplate
from src.t0.memory import Encounter


def enforce_rule(encounter: Encounter, rule: RuleTemplate | None) -> list[OptionResult]:
    # Apply M2-assigned toll to each option. sanity_penalty comes from the
    # selected rule (if any); non-stable toll always incurs the penalty.
    results: list[OptionResult] = []
    for option in encounter.options:
        m2_toll = option.get("toll", "")
        toll = m2_toll if m2_toll else "stable"
        penalty = (rule.sanity_penalty if rule else 1) if toll != "stable" else 0
        results.append(
            OptionResult(
                option_id=option["option_id"],
                label=option["label"],
                toll=toll,
                reasons=([f"m2_toll:{toll}"] if m2_toll else ["no_m2_toll"]) + list(option.get("tags", [])),
                sanity_cost=penalty,
            )
        )
    return results


# TODO: Split "soft warning" and "future hard lock" into separate enforcement stages.
