from src.t0.memory import CoreStateView, MetaStateView, OptionResult
from src.t0.core.effects import apply_option_effects
from src.runtime.session import Run


def _run(health=10, max_health=10, money=5, sanity=8) -> Run:
    return Run(
        run_id="r",
        core_state=CoreStateView(depth=1, health=health, max_health=max_health, money=money, sanity=sanity),
        meta_state=MetaStateView(),
    )


def _result(sanity_cost: int = 0, toll: str = "stable") -> OptionResult:
    return OptionResult(option_id="opt", label="opt", toll=toll, reasons=[], sanity_cost=sanity_cost)


def _opt(effects: dict) -> dict:
    return {"option_id": "opt", "metadata": {"effects": effects}}


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------

def test_health_increases() -> None:
    run = _run(health=5)
    apply_option_effects(run, _opt({"health_delta": 3}), _result())
    assert run.core_state.health == 8


def test_health_clamped_at_max() -> None:
    run = _run(health=9, max_health=10)
    apply_option_effects(run, _opt({"health_delta": 5}), _result())
    assert run.core_state.health == 10


def test_health_clamped_at_zero() -> None:
    run = _run(health=2)
    apply_option_effects(run, _opt({"health_delta": -9}), _result())
    assert run.core_state.health == 0


# ---------------------------------------------------------------------------
# money
# ---------------------------------------------------------------------------

def test_money_increases() -> None:
    run = _run(money=3)
    apply_option_effects(run, _opt({"money_delta": 4}), _result())
    assert run.core_state.money == 7


def test_money_clamped_at_zero() -> None:
    run = _run(money=1)
    apply_option_effects(run, _opt({"money_delta": -10}), _result())
    assert run.core_state.money == 0


# ---------------------------------------------------------------------------
# sanity — net = effects.sanity_delta - selected_result.sanity_cost
# ---------------------------------------------------------------------------

def test_sanity_net_from_effects_and_rule_cost() -> None:
    run = _run(sanity=8)
    # effects give +1, rule costs 2 → net -1
    apply_option_effects(run, _opt({"sanity_delta": 1}), _result(sanity_cost=2))
    assert run.core_state.sanity == 7


def test_sanity_synced_to_meta_state() -> None:
    run = _run(sanity=8)
    apply_option_effects(run, _opt({"sanity_delta": 0}), _result(sanity_cost=3))
    assert run.meta_state.sanity == run.core_state.sanity


def test_sanity_clamped_at_zero() -> None:
    run = _run(sanity=1)
    apply_option_effects(run, _opt({"sanity_delta": 0}), _result(sanity_cost=5))
    assert run.core_state.sanity == 0


# ---------------------------------------------------------------------------
# marks / events / traumas
# ---------------------------------------------------------------------------

def test_add_marks_appended_to_meta_state() -> None:
    run = _run()
    apply_option_effects(run, _opt({"add_marks": ["cursed", "exiled"]}), _result())
    assert "cursed" in run.meta_state.active_marks
    assert "exiled" in run.meta_state.active_marks


def test_duplicate_mark_not_added_twice() -> None:
    run = _run()
    run.meta_state.active_marks.append("cursed")
    apply_option_effects(run, _opt({"add_marks": ["cursed"]}), _result())
    assert run.meta_state.active_marks.count("cursed") == 1


def test_add_events_appended() -> None:
    run = _run()
    apply_option_effects(run, _opt({"add_events": ["gate_opened"]}), _result())
    assert "gate_opened" in run.meta_state.metadata.get("major_events", [])


def test_add_traumas_appended() -> None:
    run = _run()
    apply_option_effects(run, _opt({"add_traumas": ["witnessed_collapse"]}), _result())
    assert "witnessed_collapse" in run.meta_state.metadata.get("traumas", [])


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------

def test_notes_returned_for_stat_changes() -> None:
    run = _run(health=5, money=3, sanity=8)
    notes = apply_option_effects(
        run, _opt({"health_delta": 2, "money_delta": -1, "sanity_delta": 0}), _result(sanity_cost=1)
    )
    assert any("Health" in n for n in notes)
    assert any("Money" in n for n in notes)
    assert any("Sanity" in n for n in notes)


def test_no_notes_when_nothing_changes() -> None:
    run = _run()
    notes = apply_option_effects(run, _opt({}), _result(sanity_cost=0))
    assert notes == []
