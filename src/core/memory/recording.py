"""Helpers for recording node-local events and choices."""

from __future__ import annotations

from typing import Any

from .types import NodeChoiceRecord, NodeEvent, NodeMemory, ShockRecord


def append_node_event(node_memory: NodeMemory, event_type: str, **payload: Any) -> None:
    """Append one structured lifecycle event to the active node memory."""

    node_memory.events.append(NodeEvent(event_type=event_type, payload=payload))


def record_choice(
    node_memory: NodeMemory,
    *,
    arbitration: Any,
    selected_rule_id: str | None,
    selected_rule_theme: str | None,
    selected_result: Any,
) -> None:
    """Persist one resolved arbitration choice into node-local memory."""

    local_flags: list[str] = []
    joined_reasons = " ".join(selected_result.reasons)
    if selected_result.verdict == "destabilizing":
        local_flags.append("took_destabilizing_option")
    if "safe" in joined_reasons:
        local_flags.append("chose_safe_option")
    if any(token in joined_reasons for token in ("greedy", "luxury", "occult")):
        local_flags.append("chose_greedy_option")

    node_memory.choices_made.append(
        NodeChoiceRecord(
            context_id=arbitration.context.context_id,
            scene_type=arbitration.context.scene_type,
            active_rule_id=selected_rule_id,
            active_rule_theme=selected_rule_theme,
            player_choice=selected_result.option_id,
            destabilized=selected_result.verdict == "destabilizing",
            sanity_delta=selected_result.sanity_cost,
            local_flags=local_flags,
        )
    )

    if selected_result.verdict == "destabilizing":
        node_memory.shocks_in_node.append(
            ShockRecord(
                context_id=arbitration.context.context_id,
                rule_id=selected_rule_id,
                scene_type=arbitration.context.scene_type,
                option_id=selected_result.option_id,
                flags=local_flags.copy(),
                sanity_delta=selected_result.sanity_cost,
            )
        )

    node_memory.sanity_lost_in_node += selected_result.sanity_cost
    for flag in local_flags:
        if flag not in node_memory.important_flags:
            node_memory.important_flags.append(flag)
