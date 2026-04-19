from src.t0.memory import Encounter, OptionResult
from src.t0.memory import append_node_event, record_choice
from src.t0.memory.types import WaypointMemory


def _node() -> WaypointMemory:
    return WaypointMemory(waypoint_id="wp1", waypoint_type="crossroads", depth=1)


def _enc() -> Encounter:
    return Encounter.from_dict(
        {"context_id": "ctx", "scene_type": "crossroads", "depth": 1,
         "resources": {}, "options": []},
        owner_kind="node", owner_id="wp1",
    )


def _result(toll: str = "stable", reasons: list[str] | None = None,
            sanity_cost: int = 0) -> OptionResult:
    return OptionResult(option_id="opt_a", label="Go", toll=toll,
                        reasons=reasons or [], sanity_cost=sanity_cost)


# ---------------------------------------------------------------------------
# append_node_event
# ---------------------------------------------------------------------------

def test_append_node_event_stores_event() -> None:
    node = _node()
    append_node_event(node, "node_entered", waypoint_id="wp1")
    assert len(node.events) == 1
    assert node.events[0].event_type == "node_entered"
    assert node.events[0].payload["waypoint_id"] == "wp1"


def test_append_node_event_multiple() -> None:
    node = _node()
    append_node_event(node, "a")
    append_node_event(node, "b")
    assert [e.event_type for e in node.events] == ["a", "b"]


# ---------------------------------------------------------------------------
# record_choice — stable path
# ---------------------------------------------------------------------------

def test_record_choice_appends_choice_record() -> None:
    node = _node()
    record_choice(node, encounter=_enc(), selected_rule_id="shaken",
                  selected_rule_theme="self_preservation", selected_result=_result())
    assert len(node.choices_made) == 1
    choice = node.choices_made[0]
    assert choice.player_choice == "opt_a"
    assert choice.active_rule_id == "shaken"
    assert choice.destabilized is False


def test_record_choice_accumulates_sanity() -> None:
    node = _node()
    record_choice(node, encounter=_enc(), selected_rule_id=None,
                  selected_rule_theme=None, selected_result=_result(sanity_cost=2))
    record_choice(node, encounter=_enc(), selected_rule_id=None,
                  selected_rule_theme=None, selected_result=_result(sanity_cost=3))
    assert node.sanity_lost_in_waypoint == 5


def test_record_choice_safe_reason_adds_flag() -> None:
    node = _node()
    record_choice(node, encounter=_enc(), selected_rule_id=None,
                  selected_rule_theme=None, selected_result=_result(reasons=["safe retreat"]))
    assert "chose_safe_option" in node.choices_made[0].local_flags


def test_record_choice_greedy_reason_adds_flag() -> None:
    node = _node()
    record_choice(node, encounter=_enc(), selected_rule_id=None,
                  selected_rule_theme=None, selected_result=_result(reasons=["greedy gamble"]))
    assert "chose_greedy_option" in node.choices_made[0].local_flags


# ---------------------------------------------------------------------------
# record_choice — destabilizing path
# ---------------------------------------------------------------------------

def test_record_choice_destabilizing_sets_flag_and_shock() -> None:
    node = _node()
    record_choice(node, encounter=_enc(), selected_rule_id=None,
                  selected_rule_theme=None, selected_result=_result(toll="destabilizing"))
    assert node.choices_made[0].destabilized is True
    assert "took_destabilizing_option" in node.choices_made[0].local_flags
    assert len(node.shocks_in_waypoint) == 1


def test_destabilizing_adds_to_important_flags() -> None:
    node = _node()
    record_choice(node, encounter=_enc(), selected_rule_id=None,
                  selected_rule_theme=None, selected_result=_result(toll="destabilizing"))
    assert "took_destabilizing_option" in node.important_flags


def test_stable_does_not_add_shock() -> None:
    node = _node()
    record_choice(node, encounter=_enc(), selected_rule_id=None,
                  selected_rule_theme=None, selected_result=_result(toll="stable"))
    assert node.shocks_in_waypoint == []
