"""Map deterministic signals into a small ritual theme vocabulary."""

from __future__ import annotations

from src.core.runtime import Arbitration


def score_themes(arbitration: Arbitration, signals: dict[str, object]) -> dict[str, float]:
    """Map low-level deterministic signals into ritual themes."""

    # Theme scores are not the final verdict. They are a lightweight way to
    # say "what kind of ritual problem does this scene currently resemble?"
    scores = {
        "order": 0.0,
        "restraint": 0.0,
        "avoid_conflict": 0.0,
        "humility": 0.0,
    }

    tag_counts = signals["option_tag_counts"]
    context_tags = signals["context_tags"]

    # These heuristics are intentionally simple for the prototype: readable,
    # tunable, and easy to inspect in CLI output.
    if "branching_path" in arbitration.context.tags or "branching_path" in context_tags:
        scores["order"] += 2.0
    if tag_counts.get("safe", 0):
        scores["restraint"] += 1.5
    if tag_counts.get("greedy", 0):
        scores["restraint"] += 0.5
    if signals["low_hp"]:
        scores["avoid_conflict"] += 2.0
        scores["restraint"] += 1.0
    if tag_counts.get("elite", 0):
        scores["avoid_conflict"] += 1.0
    if "temptation" in arbitration.context.tags:
        scores["humility"] += 1.5
        scores["restraint"] += 1.0
    if arbitration.context.scene_type == "shop":
        scores["humility"] += 0.5
    if arbitration.context.scene_type == "event_branch":
        scores["order"] += 0.5

    return scores


# TODO: Replace heuristics with tunable weights loaded from config data.
