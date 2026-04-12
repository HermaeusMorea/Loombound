"""Deterministic signal extraction from arbitration input."""

from __future__ import annotations

from collections import Counter

from src.core.runtime import Arbitration


def build_signals(arbitration: Arbitration) -> dict[str, object]:
    # Collapse raw context into a small set of reusable, deterministic facts.
    # Later stages should mostly consume these signals rather than repeatedly
    # re-reading raw option data.
    option_tags = Counter(tag for option in arbitration.options for tag in option.get("tags", []))
    health = int(arbitration.context.resources.get("health", 0))
    money = int(arbitration.context.resources.get("money", 0))
    sanity = int(arbitration.context.resources.get("sanity", 0))

    return {
        "scene_type": arbitration.context.scene_type,
        "context_tags": set(arbitration.context.tags),
        "option_tag_counts": dict(option_tags),
        "has_safe_option": option_tags.get("safe", 0) > 0,
        "has_greedy_option": option_tags.get("greedy", 0) > 0,
        "has_volatile_option": option_tags.get("volatile", 0) > 0 or option_tags.get("occult", 0) > 0,
        "low_health": health <= 4,
        "high_health": health >= 8,
        "low_money": money <= 3,
        "high_money": money >= 9,
        "low_sanity": sanity <= 4,
        "high_sanity": sanity >= 8,
    }


# TODO: Expand signal extraction once real adapter-layer fields exist.
