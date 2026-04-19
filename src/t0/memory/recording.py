"""Helpers for recording waypoint-local events and choices."""

from __future__ import annotations

from typing import Any

from .types import WaypointChoiceRecord, NodeEvent, WaypointMemory, ShockRecord


def append_node_event(waypoint_memory: WaypointMemory, event_type: str, **payload: Any) -> None:
    """Append one structured lifecycle event to the active waypoint memory."""

    waypoint_memory.events.append(NodeEvent(event_type=event_type, payload=payload))


def record_choice(
    waypoint_memory: WaypointMemory,
    *,
    encounter: Any,
    selected_rule_id: str | None,
    selected_rule_theme: str | None,
    selected_result: Any,
) -> None:
    """Persist one resolved encounter choice into waypoint-local memory."""

    local_flags: list[str] = []
    joined_reasons = " ".join(selected_result.reasons)
    if selected_result.toll == "destabilizing":
        local_flags.append("took_destabilizing_option")
    if "safe" in joined_reasons:
        local_flags.append("chose_safe_option")
    if any(token in joined_reasons for token in ("greedy", "luxury", "occult")):
        local_flags.append("chose_greedy_option")

    waypoint_memory.choices_made.append(
        WaypointChoiceRecord(
            context_id=encounter.context.context_id,
            scene_type=encounter.context.scene_type,
            active_rule_id=selected_rule_id,
            active_rule_theme=selected_rule_theme,
            player_choice=selected_result.option_id,
            destabilized=selected_result.toll == "destabilizing",
            sanity_delta=selected_result.sanity_cost,
            local_flags=local_flags,
        )
    )

    if selected_result.toll == "destabilizing":
        waypoint_memory.shocks_in_waypoint.append(
            ShockRecord(
                context_id=encounter.context.context_id,
                rule_id=selected_rule_id,
                scene_type=encounter.context.scene_type,
                option_id=selected_result.option_id,
                flags=local_flags.copy(),
                sanity_delta=selected_result.sanity_cost,
            )
        )

    waypoint_memory.sanity_lost_in_waypoint += selected_result.sanity_cost
    for flag in local_flags:
        if flag not in waypoint_memory.important_flags:
            waypoint_memory.important_flags.append(flag)
