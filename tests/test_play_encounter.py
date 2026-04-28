import pytest

from src.t0.memory import CoreStateView, MetaStateView, RuleTemplate
from src.runtime.session import Run
from src.runtime.play_encounter import _play_encounter


@pytest.fixture(autouse=True)
def _silence_io(monkeypatch):
    monkeypatch.setattr("src.runtime.play_encounter.choose_index", lambda *_: 0)
    monkeypatch.setattr("src.runtime.play_encounter.pause", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_encounter_view", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_choices", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_input_panel", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_result", lambda *_: None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_run_and_waypoint(money: int = 0):
    run = Run(
        run_id="r1",
        core_state=CoreStateView(depth=1, act=1, health=10, max_health=10, money=money, sanity=8),
        meta_state=MetaStateView(),
    )
    run.core_state.scene_type = "crossroads"
    waypoint = run.start_waypoint("wp1", "crossroads", depth=1)
    return run, waypoint


def _payload_single(money_delta: int = 0) -> dict:
    """Authored encounter with one option."""
    return {
        "context_id": "enc_test",
        "scene_type": "crossroads",
        "depth": 1,
        "resources": {},
        "tags": ["branching_path"],
        "options": [
            {
                "option_id": "go",
                "label": "Press forward",
                "tags": ["safe"],
                "metadata": {"effects": {"health_delta": 0, "money_delta": money_delta, "sanity_delta": 0}},
            }
        ],
    }


def _payload_two() -> dict:
    """Authored encounter with two options for rule-selection tests."""
    return {
        "context_id": "enc_two",
        "scene_type": "crossroads",
        "depth": 1,
        "resources": {},
        "tags": ["branching_path"],
        "options": [
            {"option_id": "safe", "label": "Safe path", "tags": ["safe"], "metadata": {"effects": {"health_delta": 0, "money_delta": 0, "sanity_delta": 0}}},
            {"option_id": "risk", "label": "Risky path", "tags": ["volatile"], "metadata": {"effects": {"health_delta": -2, "money_delta": 0, "sanity_delta": -1}}},
        ],
    }


_RULE_SHAKEN = RuleTemplate.from_dict({
    "id": "shaken",
    "name": "Shaken",
    "decision_types": ["crossroads"],
    "theme": "self_preservation",
    "priority": 10,
    "required_context_tags": ["branching_path"],
    "preferred_option_tags": ["safe"],
    "forbidden_option_tags": ["volatile"],
    "sanity_penalty": 1,
})

_RULE_CLARITY = RuleTemplate.from_dict({
    "id": "clarity",
    "name": "Clarity",
    "decision_types": ["crossroads"],
    "theme": "clarity",
    "priority": 100,
    "required_context_tags": ["branching_path"],
    "preferred_option_tags": ["safe"],
    "sanity_penalty": 0,
})


class _FakePrefetch:
    """Minimal prefetch stub that returns a fixed m2_rule_id."""

    def __init__(self, rule_id: str = ""):
        self._rule_id = rule_id

    def consume_arb_effects(self, _node_id, _idx):
        return {}, self._rule_id

    def update_arc_state(self, *_a, **_kw):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_play_encounter_marks_encounter_applied() -> None:
    run, waypoint = _make_run_and_waypoint()
    _play_encounter(run, waypoint, _payload_single(), rules=[], prefetch=None,
                    arb_idx=0, saga_waypoint_id="wp1", total_arbs=1)
    assert waypoint.encounter_history[0].status == "applied"


def test_play_encounter_records_choice_in_waypoint_memory() -> None:
    run, waypoint = _make_run_and_waypoint()
    _play_encounter(run, waypoint, _payload_single(), rules=[], prefetch=None,
                    arb_idx=0, saga_waypoint_id="wp1", total_arbs=1)
    assert len(waypoint.memory.choices_made) == 1
    assert waypoint.memory.choices_made[0].player_choice is not None


def test_play_encounter_applies_money_effect_to_run() -> None:
    run, waypoint = _make_run_and_waypoint(money=0)
    _play_encounter(run, waypoint, _payload_single(money_delta=5), rules=[], prefetch=None,
                    arb_idx=0, saga_waypoint_id="wp1", total_arbs=1)
    assert run.core_state.money == 5


def test_play_encounter_no_rules_still_completes() -> None:
    run, waypoint = _make_run_and_waypoint()
    _play_encounter(run, waypoint, _payload_two(), rules=[], prefetch=None,
                    arb_idx=0, saga_waypoint_id="wp1", total_arbs=1)
    assert waypoint.encounter_history[0].status == "applied"


def test_play_encounter_kernel_picks_highest_priority_matching_rule() -> None:
    # With M2 no longer choosing rules, the symbolic kernel (select_rule) is
    # the sole selector — it picks by priority among matching rules.
    # "clarity" has priority 100, "shaken" has priority 10 → clarity wins.
    run, waypoint = _make_run_and_waypoint()
    fake_prefetch = _FakePrefetch(rule_id="shaken")  # rule_id returned, but ignored now
    _play_encounter(run, waypoint, _payload_two(), rules=[_RULE_SHAKEN, _RULE_CLARITY],
                    prefetch=fake_prefetch, arb_idx=0, saga_waypoint_id="wp1", total_arbs=1)
    assert waypoint.memory.choices_made[0].active_rule_id == "clarity"


def test_play_encounter_narration_table_neutral_fallback() -> None:
    run, waypoint = _make_run_and_waypoint()
    # Rule theme is "self_preservation", not in narration_table → falls back to "neutral"
    narration_table = {"neutral": "darkness closes in"}
    _play_encounter(run, waypoint, _payload_two(), rules=[_RULE_SHAKEN], prefetch=None,
                    arb_idx=0, saga_waypoint_id="wp1", total_arbs=1,
                    narration_table=narration_table)
    result = waypoint.encounter_history[0].result
    assert result.narration.text == "darkness closes in"
