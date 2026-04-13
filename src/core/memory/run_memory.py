from __future__ import annotations

from dataclasses import asdict

from .types import (
    NarratorMood,
    JudgePersonaState,
    NodeChoiceRecord,
    NodeEvent,
    NodeMemory,
    RunMemory,
    ShockRecord,
)


def update_after_node(run_memory: RunMemory, node_memory: NodeMemory) -> RunMemory:
    """Promote the important outcome of one finished node into run memory."""

    run_memory.sanity += node_memory.sanity_lost_in_node

    for choice in node_memory.choices_made:
        if choice.active_rule_id:
            run_memory.recent_rules.append(choice.active_rule_id)

        if choice.active_rule_theme:
            theme_key = choice.active_rule_theme
            run_memory.theme_counters[theme_key] = run_memory.theme_counters.get(theme_key, 0) + 1

        for flag in choice.local_flags:
            run_memory.behavior_counters[flag] = run_memory.behavior_counters.get(flag, 0) + 1

    run_memory.recent_rules = run_memory.recent_rules[-5:]

    for flag in node_memory.important_flags:
        run_memory.behavior_counters[flag] = run_memory.behavior_counters.get(flag, 0) + 1

    if node_memory.shocks_in_node:
        run_memory.recent_shocks.extend(node_memory.shocks_in_node)
        run_memory.recent_shocks = run_memory.recent_shocks[-5:]
        run_memory.narrator_mood.severity += len(node_memory.shocks_in_node)
        run_memory.narrator_mood.dread += 1
        if any("greedy" in flag for record in node_memory.shocks_in_node for flag in record.flags):
            run_memory.narrator_mood.temptation += 1
    else:
        run_memory.narrator_mood.leniency += 1

    if node_memory.node_summary:
        run_memory.important_incidents.append(node_memory.node_summary)
        run_memory.important_incidents = run_memory.important_incidents[-5:]

    return run_memory


def run_memory_to_dict(run_memory: RunMemory) -> dict:
    """Serialize run memory into JSON-friendly nested dictionaries."""

    return asdict(run_memory)


__all__ = [
    "NarratorMood",
    "JudgePersonaState",
    "NodeChoiceRecord",
    "NodeEvent",
    "NodeMemory",
    "RunMemory",
    "ShockRecord",
    "update_after_node",
    "run_memory_to_dict",
]
