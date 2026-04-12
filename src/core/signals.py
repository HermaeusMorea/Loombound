from __future__ import annotations

from collections import Counter

from src.core.models import ChoiceContext


def build_signals(context: ChoiceContext) -> dict[str, object]:
    # Collapse raw context into a small set of reusable, deterministic facts.
    # Later stages should mostly consume these signals rather than repeatedly
    # re-reading raw option data.
    option_tags = Counter(tag for option in context.options for tag in option.tags)
    hp_ratio = float(context.resources.get("hp_ratio", 1.0))
    gold = int(context.resources.get("gold", 0))

    return {
        "decision_type": context.decision_type,
        "context_tags": set(context.tags),
        "option_tag_counts": dict(option_tags),
        "has_safe_option": option_tags.get("safe", 0) > 0,
        "has_greedy_option": option_tags.get("greedy", 0) > 0,
        "has_elite_route": option_tags.get("elite", 0) > 0,
        "low_hp": hp_ratio <= 0.40,
        "high_hp": hp_ratio >= 0.75,
        "low_gold": gold <= 80,
        "high_gold": gold >= 180,
    }


# TODO: Expand signal extraction once real adapter-layer fields exist.
