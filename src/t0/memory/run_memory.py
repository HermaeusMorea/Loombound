from __future__ import annotations

from dataclasses import asdict

from .types import (
    NarratorMood,
    JudgePersonaState,
    WaypointChoiceRecord,
    NodeEvent,
    WaypointMemory,
    RunMemory,
    ShockRecord,
)


def update_after_waypoint(run_memory: RunMemory, waypoint_memory: WaypointMemory) -> RunMemory:
    """Promote the important outcome of one finished waypoint into run memory."""

    run_memory.sanity += waypoint_memory.sanity_lost_in_waypoint

    for choice in waypoint_memory.choices_made:
        if choice.active_rule_id:
            run_memory.recent_rules.append(choice.active_rule_id)

        if choice.active_rule_theme:
            theme_key = choice.active_rule_theme
            run_memory.theme_counters[theme_key] = run_memory.theme_counters.get(theme_key, 0) + 1

        for flag in choice.local_flags:
            run_memory.behavior_counters[flag] = run_memory.behavior_counters.get(flag, 0) + 1

    run_memory.recent_rules = run_memory.recent_rules[-5:]

    if waypoint_memory.shocks_in_waypoint:
        run_memory.recent_shocks.extend(waypoint_memory.shocks_in_waypoint)
        run_memory.recent_shocks = run_memory.recent_shocks[-5:]
        run_memory.narrator_mood.severity += len(waypoint_memory.shocks_in_waypoint)
        run_memory.narrator_mood.dread += 1
        if any("greedy" in flag for record in waypoint_memory.shocks_in_waypoint for flag in record.flags):
            run_memory.narrator_mood.temptation += 1
    else:
        run_memory.narrator_mood.leniency += 1

    if waypoint_memory.waypoint_summary:
        run_memory.important_incidents.append(waypoint_memory.waypoint_summary)
        run_memory.important_incidents = run_memory.important_incidents[-5:]

    return run_memory


def run_memory_to_dict(run_memory: RunMemory) -> dict:
    """Serialize run memory into JSON-friendly nested dictionaries."""

    return asdict(run_memory)


__all__ = [
    "NarratorMood",
    "JudgePersonaState",
    "WaypointChoiceRecord",
    "NodeEvent",
    "WaypointMemory",
    "RunMemory",
    "ShockRecord",
    "update_after_waypoint",
    "run_memory_to_dict",
]
