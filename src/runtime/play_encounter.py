"""Encounter execution layer for the Loombound runtime."""
from __future__ import annotations

import copy

from src.t0.memory import EncounterResult, append_node_event, record_choice
from src.t0.memory.models import NarrationBlock
from src.t0.core import (
    apply_option_effects,
    build_selection_trace,
    build_signals,
    enforce_rule,
    evaluate_rules,
    pause,
    render_choices,
    render_encounter_view,
    render_input_panel,
    render_result,
    select_rule,
)
from src.t2.core import PrefetchCache
from src.t2.core.collector import build_classifier_input
from src.runtime.play_runtime import choose_index, sync_encounter_resources


def _overlay_effects(payload: dict, opus_effects: dict[str, dict]) -> dict:
    """Return a new payload with Opus-assigned numeric effect values patched in.

    Only the three stat keys are touched; add_events / add_marks written by
    C1-generated content is preserved.
    """
    patched = copy.deepcopy(payload)
    for opt in patched.get("options", []):
        opt_id = opt.get("option_id", "")
        if opt_id in opus_effects:
            eff = opt.setdefault("metadata", {}).setdefault("effects", {})
            for key in ("health_delta", "money_delta", "sanity_delta"):
                eff[key] = opus_effects[opt_id].get(key, 0)
            toll = opus_effects[opt_id].get("toll", "")
            if toll:
                opt["toll"] = toll
    return patched


def _play_encounter(
    run,
    waypoint,
    payload: dict[str, object],
    rules,
    prefetch: PrefetchCache | None,
    arb_idx: int,
    saga_waypoint_id: str,
    total_arbs: int,
    narration_table: dict | None = None,
) -> None:
    # Consume M2-assigned effects and rule selection (may be empty on cache miss)
    m2_effects: dict[str, dict] = {}
    m2_rule_id: str = ""
    if prefetch is not None:
        m2_effects, m2_rule_id = prefetch.consume_arb_effects(saga_waypoint_id, arb_idx)
        if m2_effects:
            payload = _overlay_effects(payload, m2_effects)

    encounter = waypoint.load_current_encounter(payload)
    sync_encounter_resources(run, encounter)
    append_node_event(
        waypoint.memory,
        "encounter_loaded",
        encounter_id=encounter.encounter_id,
        scene_type=encounter.context.scene_type,
        context_id=encounter.context.context_id,
    )

    signals = build_signals(encounter)
    evaluations = evaluate_rules(encounter, rules)
    waypoint.rule_state.reset_for_encounter()
    waypoint.rule_state.record_evaluations(evaluations)

    # M2 rule selection is primary; deterministic evaluation is the fallback.
    m2_rule = next((r for r in rules if r.id == m2_rule_id), None) if m2_rule_id else None
    _sel_eval = None if m2_rule else select_rule(
        evaluations, rule_system=run.rule_system, run_memory=run.memory
    )
    selected_rule = m2_rule or (_sel_eval.rule if _sel_eval else None)

    waypoint.rule_state.record_selected_rule(selected_rule.id if selected_rule else None)
    waypoint.rule_state.record_selection_trace(
        build_selection_trace(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    )
    run.rule_system.record_selected_rule(selected_rule.id if selected_rule else None)
    append_node_event(
        waypoint.memory,
        "rule_selected",
        encounter_id=encounter.encounter_id,
        selected_rule_id=selected_rule.id if selected_rule else None,
        matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
        source="m2" if m2_rule else "kernel",
    )

    option_results = enforce_rule(encounter, selected_rule)

    rule_theme = selected_rule.theme if selected_rule else "neutral"
    narration_text = ""
    if narration_table is not None:
        narration_text = (
            narration_table.get(rule_theme)
            or narration_table.get("neutral")
            or ""
        )

    render_encounter_view(run, encounter, selected_rule)
    render_choices(option_results)
    render_input_panel("Choose an option")

    choice_index = choose_index("> ", len(option_results))
    chosen_result = option_results[choice_index]
    encounter.select_option(chosen_result.option_id)
    selected_option = encounter.get_option(chosen_result.option_id) or {}

    record_choice(
        waypoint.memory,
        encounter=encounter,
        selected_rule_id=selected_rule.id if selected_rule else None,
        selected_rule_theme=selected_rule.theme if selected_rule else None,
        selected_result=chosen_result,
    )
    append_node_event(
        waypoint.memory,
        "option_chosen",
        encounter_id=encounter.encounter_id,
        option_id=chosen_result.option_id,
        toll=chosen_result.toll,
        sanity_delta=chosen_result.sanity_cost,
    )

    # Fire-and-forget Opus call: updates arc entry_id + assigns effects for next arb.
    # Within a waypoint: next_waypoint_id = saga_waypoint_id, next_arb_idx = arb_idx + 1.
    # Last arb of a waypoint: pass None/None — only entry_id is updated; the main loop
    # triggers the Opus call for the first arb of the chosen next waypoint.
    if prefetch is not None:
        _is_last = arb_idx >= total_arbs - 1
        _next_node = saga_waypoint_id if not _is_last else None
        _next_idx  = arb_idx + 1       if not _is_last else None
        quasi = build_classifier_input(
            run.core_state, run.memory, list(run.waypoint_history),
            current_waypoint_memory=waypoint.memory,
        )
        prefetch.update_arc_state(quasi, _next_node, _next_idx)

    narration = NarrationBlock(text=narration_text)
    applied_notes = apply_option_effects(run, selected_option, chosen_result)
    encounter.set_result(
        EncounterResult(
            selected_rule_id=selected_rule.id if selected_rule else None,
            matched_rule_ids=[item.rule.id for item in evaluations if item.matched],
            option_results=option_results,
            sanity_delta=chosen_result.sanity_cost,
            narration=narration,
        )
    )
    encounter.mark_applied()
    waypoint.close_current_encounter()
    append_node_event(
        waypoint.memory,
        "encounter_finalized",
        encounter_id=encounter.encounter_id,
        selected_rule_id=selected_rule.id if selected_rule else None,
        player_choice=chosen_result.option_id,
    )

    render_result(run, chosen_result, narration, applied_notes)
    pause()
