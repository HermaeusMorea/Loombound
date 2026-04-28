"""Encounter execution layer for the Loombound runtime."""
from __future__ import annotations

from src.shared import config as _config
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
from src.t0.core.effects_templater import generate_effects
from src.t2.core import PrefetchCache
from src.t2.core.arc_state import RunStateSnapshot, needs_reclassification
from src.t2.core.collector import _band, build_classifier_input
from src.runtime.play_runtime import choose_index, sync_encounter_resources


def _bands_from_core_state(core_state) -> dict[str, str]:
    max_h = core_state.max_health or 100
    return {
        "health": _band(core_state.health, 0, max_h),
        "money":  _band(core_state.money,  0, _config.MONEY_MAX),
        "sanity": _band(core_state.sanity, 0, 100),
    }


def _apply_templated_effects(encounter, selected_rule, bands: dict[str, str], core_state) -> None:
    """Populate per-option `metadata.effects` and `toll` from the templater.

    When no rule is selected, we do NOT override existing effects — authored
    encounters and C1-seeded skeletons keep whatever values they already carry.

    Delta scales derive from the saga's own max_health (falls back to 100);
    sanity is always on a 0..100 scale (enforced by effects.py).
    """
    if selected_rule is None:
        return
    effects_map = generate_effects(
        selected_rule,
        encounter.options,
        bands,
        max_health=core_state.max_health or 100,
    )
    for opt in encounter.options:
        opt_id = opt.get("option_id", "")
        eff = effects_map.get(opt_id)
        if not eff:
            continue
        meta = opt.setdefault("metadata", {})
        stored = meta.setdefault("effects", {})
        stored["health_delta"] = eff["health_delta"]
        stored["money_delta"]  = eff["money_delta"]
        stored["sanity_delta"] = eff["sanity_delta"]
        if eff.get("toll"):
            opt["toll"] = eff["toll"]


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
    # Sync with any in-flight M2 arc classification so _current_arc_id is fresh
    # before the templater runs. Effects + rule selection are both deterministic
    # now: rule_selector picks symbolically, effects_templater generates deltas.
    if prefetch is not None:
        prefetch.consume_arb_effects(saga_waypoint_id, arb_idx)

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

    # Symbolic rule selection is the sole path.
    _sel_eval = select_rule(evaluations, rule_system=run.rule_system, run_memory=run.memory)
    selected_rule = _sel_eval.rule if _sel_eval else None

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
        source="kernel",
    )

    # Generate per-option effects deterministically from the selected rule +
    # current quasi-state bands. Patches `metadata.effects` and `toll` on each
    # option in place so enforce_rule and apply_option_effects see them.
    _apply_templated_effects(
        encounter,
        selected_rule,
        _bands_from_core_state(run.core_state),
        run.core_state,
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

    # Snapshot before applying effects so we can detect band crossings caused
    # by this choice. The waypoint-start M2 fire (in play_cli at transition
    # time) covers baseline classification; we only re-fire mid-waypoint when
    # something meaningful changes.
    prev_snapshot = RunStateSnapshot.from_run(run)

    narration = NarrationBlock(text=narration_text)
    applied_notes = apply_option_effects(run, selected_option, chosen_result)

    curr_snapshot = RunStateSnapshot.from_run(run)

    # Conditional mid-waypoint M2 fire: only when a band flipped, a mark was
    # added/removed, or a trauma was recorded.
    if prefetch is not None and needs_reclassification(prev_snapshot, curr_snapshot):
        _is_last = arb_idx >= total_arbs - 1
        _next_waypoint = saga_waypoint_id if not _is_last else None
        _next_idx  = arb_idx + 1       if not _is_last else None
        quasi = build_classifier_input(
            run.core_state, run.memory, list(run.waypoint_history),
            current_waypoint_memory=waypoint.memory,
        )
        prefetch.update_arc_state(quasi, _next_waypoint, _next_idx)
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
