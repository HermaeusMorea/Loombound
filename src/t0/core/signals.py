"""Deterministic signal extraction from encounter input."""

from __future__ import annotations

from collections import Counter

from src.t0.memory import Encounter

_LOW_HEALTH = 4
_HIGH_HEALTH = 8
_LOW_MONEY = 3
_HIGH_MONEY = 9
_LOW_SANITY = 4
_HIGH_SANITY = 8


def build_signals(encounter: Encounter) -> dict[str, object]:
    # Collapse raw context into a small set of reusable, deterministic facts.
    # Later stages should mostly consume these signals rather than repeatedly
    # re-reading raw option data.
    option_tags = Counter(tag for option in encounter.options for tag in option.get("tags", []))
    health = int(encounter.context.resources.get("health") or 0)
    money = int(encounter.context.resources.get("money") or 0)
    sanity = int(encounter.context.resources.get("sanity") or 0)

    return {
        "scene_type": encounter.context.scene_type,
        "context_tags": set(encounter.context.tags),
        "option_tag_counts": dict(option_tags),
        "has_safe_option": option_tags.get("safe", 0) > 0,
        "has_greedy_option": option_tags.get("greedy", 0) > 0,
        "has_volatile_option": option_tags.get("volatile", 0) > 0 or option_tags.get("occult", 0) > 0,
        "low_health": health <= _LOW_HEALTH,
        "high_health": health >= _HIGH_HEALTH,
        "low_money": money <= _LOW_MONEY,
        "high_money": money >= _HIGH_MONEY,
        "low_sanity": sanity <= _LOW_SANITY,
        "high_sanity": sanity >= _HIGH_SANITY,
    }


# TODO: Expand signal extraction once real adapter-layer fields exist.
