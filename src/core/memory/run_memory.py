from __future__ import annotations

from dataclasses import asdict

from .types import (
    JudgeMood,
    JudgePersonaState,
    NodeChoiceRecord,
    NodeEvent,
    NodeMemory,
    RunMemory,
    ViolationRecord,
)


def update_after_node(run_memory: RunMemory, node_memory: NodeMemory) -> RunMemory:
    """Promote the important outcome of one finished node into run memory."""

    run_memory.ritual_collapse += node_memory.collapse_gained_in_node

    for choice in node_memory.choices_made:
        if choice.active_rule_id:
            run_memory.recent_edicts.append(choice.active_rule_id)
        run_memory.recent_edicts = run_memory.recent_edicts[-5:]

        if choice.active_rule_theme:
            theme_key = choice.active_rule_theme
            run_memory.theme_counters[theme_key] = run_memory.theme_counters.get(theme_key, 0) + 1

        for flag in choice.local_flags:
            run_memory.behavior_counters[flag] = run_memory.behavior_counters.get(flag, 0) + 1

    if node_memory.violations_in_node:
        run_memory.recent_violations.extend(node_memory.violations_in_node)
        run_memory.recent_violations = run_memory.recent_violations[-5:]
        run_memory.judge_mood.severity += len(node_memory.violations_in_node)
        run_memory.judge_mood.suspicion += 1
        if any("greedy" in flag for record in node_memory.violations_in_node for flag in record.flags):
            run_memory.judge_mood.anti_greed += 1
    else:
        run_memory.judge_mood.leniency += 1

    for flag in node_memory.important_flags:
        run_memory.behavior_counters[flag] = run_memory.behavior_counters.get(flag, 0) + 1

    if node_memory.node_summary:
        run_memory.important_incidents.append(node_memory.node_summary)
        run_memory.important_incidents = run_memory.important_incidents[-5:]

    return run_memory


def update_after_choice(run_memory: RunMemory, node_memory: NodeMemory) -> RunMemory:
    """Backward-compatible alias kept while runtime callers are being renamed."""

    return update_after_node(run_memory, node_memory)


def run_memory_to_dict(run_memory: RunMemory) -> dict:
    """Serialize run memory into JSON-friendly nested dictionaries."""

    return asdict(run_memory)


__all__ = [
    "JudgeMood",
    "JudgePersonaState",
    "NodeChoiceRecord",
    "NodeEvent",
    "NodeMemory",
    "RunMemory",
    "ViolationRecord",
    "update_after_node",
    "run_memory_to_dict",
    "update_after_choice",
]
