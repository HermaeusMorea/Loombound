"""Pure helpers: arc-state row → tendency dict, and scene skeleton + arc merge."""
from __future__ import annotations

from typing import Any

from .types import EncounterSeed, EncounterOptionSeed


def arc_row_to_tendency(arc_row: Any) -> dict[str, str]:
    """Extract tendency fields from an arc-state catalog row."""
    return {
        "entry_id": str(getattr(arc_row, "entry_id", "")),
        "arc_trajectory": getattr(arc_row, "arc_trajectory", ""),
        "world_pressure": getattr(arc_row, "world_pressure", ""),
        "narrative_pacing": getattr(arc_row, "narrative_pacing", ""),
        "pending_intent": getattr(arc_row, "pending_intent", ""),
    }


def merge_preloaded_seed(
    skeleton: Any,
    arc_row: Any,
) -> EncounterSeed:
    """Blend a scene skeleton with the runtime arc-state tendency.

    Effects in the seed come from the T1 cache (Haiku-generated placeholders).
    Haiku per-option effects are applied separately at play time via play_cli's
    _overlay_effects, which patches the expanded payload dict directly.
    """
    raw_options = skeleton.options or []
    arb_options = [
        EncounterOptionSeed(
            option_id=o.get("option_id", f"opt_{i}"),
            intent=o.get("intent", ""),
            tags=o.get("tags", []),
            effects=o.get("effects", {}),
        )
        for i, o in enumerate(raw_options)
    ]

    tendency = arc_row_to_tendency(arc_row)
    tendency_text = (
        f"arc_trajectory={tendency['arc_trajectory']}, "
        f"world_pressure={tendency['world_pressure']}, "
        f"narrative_pacing={tendency['narrative_pacing']}, "
        f"pending_intent={tendency['pending_intent']}"
    )

    return EncounterSeed(
        scene_type=skeleton.scene_type,
        scene_concept=(
            f"{skeleton.scene_concept}\n"
            f"Runtime arc tendency to honor: {tendency_text}."
        ),
        sanity_axis=(
            f"{skeleton.sanity_axis}\n"
            f"Current dramatic emphasis: {tendency['world_pressure']} pressure, "
            f"{tendency['narrative_pacing']} pacing, {tendency['pending_intent']} intent."
        ),
        options=arb_options,
        tendency=tendency,
    )
