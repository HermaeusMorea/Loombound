from src.t0.memory import update_after_node, RunMemory
from src.t0.memory.types import WaypointMemory, WaypointChoiceRecord, ShockRecord


def _node(waypoint_id: str = "wp1") -> WaypointMemory:
    return WaypointMemory(waypoint_id=waypoint_id, waypoint_type="crossroads", depth=1)


def _choice(rule_id: str | None = None, theme: str | None = None,
            flags: list[str] | None = None, sanity_delta: int = 0) -> WaypointChoiceRecord:
    return WaypointChoiceRecord(
        context_id="ctx",
        scene_type="crossroads",
        active_rule_id=rule_id,
        active_rule_theme=theme,
        player_choice="opt_a",
        sanity_delta=sanity_delta,
        local_flags=flags or [],
    )


# ---------------------------------------------------------------------------
# sanity accumulation
# ---------------------------------------------------------------------------

def test_sanity_accumulated_from_node() -> None:
    mem = RunMemory()
    node = _node()
    node.sanity_lost_in_node = 3
    update_after_node(mem, node)
    assert mem.sanity == 3


def test_sanity_accumulates_across_multiple_nodes() -> None:
    mem = RunMemory()
    for loss in (2, 1, 3):
        node = _node()
        node.sanity_lost_in_node = loss
        update_after_node(mem, node)
    assert mem.sanity == 6


# ---------------------------------------------------------------------------
# recent_rules window (keeps last 5)
# ---------------------------------------------------------------------------

def test_recent_rules_appended() -> None:
    mem = RunMemory()
    node = _node()
    node.choices_made.append(_choice(rule_id="shaken"))
    update_after_node(mem, node)
    assert "shaken" in mem.recent_rules


def test_recent_rules_window_capped_at_five() -> None:
    mem = RunMemory()
    for i in range(7):
        node = _node()
        node.choices_made.append(_choice(rule_id=f"rule_{i}"))
        update_after_node(mem, node)
    assert len(mem.recent_rules) == 5
    assert mem.recent_rules[-1] == "rule_6"


def test_none_rule_id_not_appended() -> None:
    mem = RunMemory()
    node = _node()
    node.choices_made.append(_choice(rule_id=None))
    update_after_node(mem, node)
    assert mem.recent_rules == []


# ---------------------------------------------------------------------------
# theme_counters
# ---------------------------------------------------------------------------

def test_theme_counter_incremented() -> None:
    mem = RunMemory()
    node = _node()
    node.choices_made.append(_choice(theme="self_preservation"))
    node.choices_made.append(_choice(theme="self_preservation"))
    update_after_node(mem, node)
    assert mem.theme_counters["self_preservation"] == 2


def test_theme_counter_accumulates_across_nodes() -> None:
    mem = RunMemory()
    for _ in range(3):
        node = _node()
        node.choices_made.append(_choice(theme="clarity"))
        update_after_node(mem, node)
    assert mem.theme_counters["clarity"] == 3


# ---------------------------------------------------------------------------
# behavior_counters (from local_flags)
# ---------------------------------------------------------------------------

def test_behavior_counters_from_flags() -> None:
    mem = RunMemory()
    node = _node()
    node.choices_made.append(_choice(flags=["took_destabilizing_option"]))
    update_after_node(mem, node)
    assert mem.behavior_counters["took_destabilizing_option"] == 1


# ---------------------------------------------------------------------------
# shocks + narrator_mood
# ---------------------------------------------------------------------------

def test_shock_increments_severity_and_dread() -> None:
    mem = RunMemory()
    node = _node()
    node.shocks_in_node.append(ShockRecord(
        context_id="ctx", rule_id=None, scene_type="crossroads",
        option_id="risk", flags=[], sanity_delta=2,
    ))
    update_after_node(mem, node)
    assert mem.narrator_mood.severity == 1
    assert mem.narrator_mood.dread == 1


def test_greedy_shock_increments_temptation() -> None:
    mem = RunMemory()
    node = _node()
    node.shocks_in_node.append(ShockRecord(
        context_id="ctx", rule_id=None, scene_type="crossroads",
        option_id="gold", flags=["chose_greedy_option"], sanity_delta=1,
    ))
    update_after_node(mem, node)
    assert mem.narrator_mood.temptation == 1


def test_no_shocks_increments_leniency() -> None:
    mem = RunMemory()
    node = _node()
    update_after_node(mem, node)
    assert mem.narrator_mood.leniency == 1


def test_recent_shocks_window_capped_at_five() -> None:
    mem = RunMemory()
    for i in range(7):
        node = _node()
        node.shocks_in_node.append(ShockRecord(
            context_id=f"ctx_{i}", rule_id=None, scene_type="crossroads",
            option_id="risk", flags=[], sanity_delta=1,
        ))
        update_after_node(mem, node)
    assert len(mem.recent_shocks) == 5


# ---------------------------------------------------------------------------
# important_incidents window (keeps last 5)
# ---------------------------------------------------------------------------

def test_node_summary_appended_to_incidents() -> None:
    mem = RunMemory()
    node = _node()
    node.node_summary = "crossroads:2_encounters:sanity=1"
    update_after_node(mem, node)
    assert mem.important_incidents == ["crossroads:2_encounters:sanity=1"]


def test_incidents_window_capped_at_five() -> None:
    mem = RunMemory()
    for i in range(7):
        node = _node()
        node.node_summary = f"summary_{i}"
        update_after_node(mem, node)
    assert len(mem.important_incidents) == 5
    assert mem.important_incidents[-1] == "summary_6"
