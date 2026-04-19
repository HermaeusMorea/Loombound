"""State application helpers for selected encounter options."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.t0.memory.models import OptionPayload

if TYPE_CHECKING:
    from src.runtime.session import Run


def _clamp(value: int, minimum: int = 0, maximum: int | None = None) -> int:
    """Clamp a state value into an allowed range."""

    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def apply_option_effects(run: Run, option: OptionPayload, selected_result: Any) -> list[str]:
    """Apply authored option effects plus the judged sanity cost to the active run."""

    effects = option.get("metadata", {}).get("effects", {})
    notes: list[str] = []

    # Pre-validate all delta values before any state mutation.
    try:
        health_delta = int(effects.get("health_delta", 0))
        money_delta = int(effects.get("money_delta", 0))
        direct_sanity_delta = int(effects.get("sanity_delta", 0))
        sanity_loss = int(selected_result.sanity_cost)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"apply_option_effects: invalid effect value — {exc}") from exc

    if run.core_state.health is not None:
        run.core_state.health = _clamp(run.core_state.health + health_delta, 0, run.core_state.max_health or 100)
        if health_delta:
            notes.append(f"Health {'+' if health_delta > 0 else ''}{health_delta}")

    if run.core_state.money is not None:
        run.core_state.money = _clamp(run.core_state.money + money_delta, 0)
        if money_delta:
            notes.append(f"Money {'+' if money_delta > 0 else ''}{money_delta}")

    if run.core_state.sanity is not None:
        net_sanity = direct_sanity_delta - sanity_loss
        run.core_state.sanity = _clamp(run.core_state.sanity + net_sanity, 0, 100)
        run.meta_state.sanity = run.core_state.sanity
        if net_sanity:
            notes.append(f"Sanity {'+' if net_sanity > 0 else ''}{net_sanity}")

    for condition in effects.get("add_marks", []):
        if condition not in run.meta_state.active_marks:
            run.meta_state.active_marks.append(condition)
            notes.append(f"Gained mark: {condition}")

    major_events = run.meta_state.metadata.setdefault("major_events", [])
    for event in effects.get("add_events", []):
        major_events.append(event)
        notes.append(f"Recorded event: {event}")

    traumas = run.meta_state.metadata.setdefault("traumas", [])
    for trauma in effects.get("add_traumas", []):
        traumas.append(trauma)
        notes.append(f"Recorded trauma: {trauma}")

    return notes
