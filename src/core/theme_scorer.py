from __future__ import annotations

from src.core.models import ChoiceContext


def score_themes(context: ChoiceContext, signals: dict[str, object]) -> dict[str, float]:
    scores = {
        "order": 0.0,
        "restraint": 0.0,
        "avoid_conflict": 0.0,
        "humility": 0.0,
    }

    tag_counts = signals["option_tag_counts"]
    context_tags = signals["context_tags"]

    if "branching_path" in context.tags or "branching_path" in context_tags:
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
    if "temptation" in context.tags:
        scores["humility"] += 1.5
        scores["restraint"] += 1.0
    if context.decision_type == "shop":
        scores["humility"] += 0.5
    if context.decision_type == "event_branch":
        scores["order"] += 0.5

    return scores


# TODO: Replace heuristics with tunable weights loaded from config data.

