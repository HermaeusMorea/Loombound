"""Render optional narration around already-computed verdicts."""

from __future__ import annotations

from src.t0.memory import NarrationBlock, RuleTemplate
from src.t0.memory import Encounter


def render_narration(
    encounter: Encounter,
    rule: RuleTemplate | None,
    templates: dict[str, list[str]] | None,
    enabled: bool = True,
) -> NarrationBlock:
    # Narration is optional by design. The verdict should still exist even if
    # this function returns an empty block.
    if not enabled or not templates:
        return NarrationBlock()

    if rule is None:
        opening = _pick(templates, "opening_neutral")
        return NarrationBlock(
            opening=opening.format(decision_type=encounter.context.scene_type),
            judgement="The scene is logged, but no stabilizing pattern has been locked in yet.",
            warning="No sanity risk has been marked.",
        )

    opening_key = f"opening_{rule.theme}"
    judgement_key = "judgement_default"
    warning_key = "warning_default"

    # The current prototype always picks the first template for deterministic
    # output. Randomization or LLM rewriting can be layered on later.
    return NarrationBlock(
        opening=_pick(templates, opening_key).format(decision_type=encounter.context.scene_type),
        judgement=_pick(templates, judgement_key).format(rule_name=rule.name, theme=rule.theme),
        warning=_pick(templates, warning_key).format(penalty=rule.sanity_penalty),
    )


def _pick(templates: dict[str, list[str]], key: str) -> str:
    # Deterministic fallback order keeps CLI output stable and easy to test.
    values = templates.get(key) or templates.get("fallback") or [""]
    return values[0]


# TODO: Allow per-rule narration overrides and richer placeholder filling.
