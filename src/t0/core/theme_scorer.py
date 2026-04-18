"""Map deterministic signals into a small sanity-survival theme vocabulary."""

from __future__ import annotations

from src.t0.memory import Arbitration


def score_themes(arbitration: Arbitration, signals: dict[str, object]) -> dict[str, float]:
    """Map low-level deterministic signals into sanity-survival themes."""

    # Theme scores are not the final verdict. They are a lightweight way to
    # say "what kind of pressure does this scene currently resemble?"
    scores = {
        "clarity": 0.0,
        "composure": 0.0,
        "self_preservation": 0.0,
        "detachment": 0.0,
    }

    tag_counts = signals["option_tag_counts"]
    context_tags = signals["context_tags"]

    # These heuristics are intentionally simple for the prototype: readable,
    # tunable, and easy to inspect in CLI output.
    if "branching_path" in context_tags:
        scores["clarity"] += 2.0
    if tag_counts.get("safe", 0):
        scores["composure"] += 1.5
    if tag_counts.get("greedy", 0):
        scores["composure"] += 0.5
    if signals["low_health"]:
        scores["self_preservation"] += 2.0
        scores["composure"] += 1.0
    if signals["low_sanity"]:
        scores["self_preservation"] += 1.5
        scores["clarity"] += 0.5
    if tag_counts.get("volatile", 0) or tag_counts.get("occult", 0):
        scores["self_preservation"] += 1.0
    if "temptation" in context_tags:
        scores["detachment"] += 1.5
        scores["composure"] += 1.0
    if arbitration.context.scene_type == "market_offer":
        scores["detachment"] += 0.5
    if arbitration.context.scene_type in {"omens_choice", "crossroads"}:
        scores["clarity"] += 0.5

    return scores


# TODO: Replace heuristics with tunable weights loaded from config data.
