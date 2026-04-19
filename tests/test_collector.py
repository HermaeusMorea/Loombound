from src.t0.memory import CoreStateView
from src.t0.memory.types import WaypointMemory, RunMemory, ShockRecord
from src.t2.core.collector import build_scene_history_entry, _band, _direction


# ---------------------------------------------------------------------------
# _band
# ---------------------------------------------------------------------------

def test_band_very_low() -> None:
    assert _band(0, 0, 10) == "very_low"    # ratio 0.0


def test_band_low() -> None:
    assert _band(3, 0, 10) == "low"          # ratio 0.3


def test_band_moderate() -> None:
    assert _band(5, 0, 10) == "moderate"     # ratio 0.5


def test_band_high() -> None:
    assert _band(7, 0, 10) == "high"         # ratio 0.7


def test_band_very_high() -> None:
    assert _band(10, 0, 10) == "very_high"   # ratio 1.0


def test_band_none_returns_unknown() -> None:
    assert _band(None, 0, 10) == "unknown"


def test_band_degenerate_range_returns_moderate() -> None:
    assert _band(5, 5, 5) == "moderate"


# ---------------------------------------------------------------------------
# _direction
# ---------------------------------------------------------------------------

def test_direction_rising() -> None:
    assert _direction(8, 5) == "rising"


def test_direction_falling() -> None:
    assert _direction(3, 7) == "falling"


def test_direction_stable() -> None:
    assert _direction(5, 5) == "stable"


def test_direction_none_value_returns_stable() -> None:
    assert _direction(None, 5) == "stable"


def test_direction_none_previous_returns_stable() -> None:
    assert _direction(5, None) == "stable"


# ---------------------------------------------------------------------------
# build_scene_history_entry — pressure_level
# ---------------------------------------------------------------------------

def _core(sanity: int = 8, max_health: int = 10) -> CoreStateView:
    return CoreStateView(depth=2, act=1, health=8, max_health=max_health, money=3, sanity=sanity)


def _node(sanity_lost: int = 0, shocks: int = 0, flags: list[str] | None = None) -> WaypointMemory:
    m = WaypointMemory(waypoint_id="wp1", waypoint_type="crossroads", depth=2)
    m.sanity_lost_in_node = sanity_lost
    if flags:
        m.important_flags = list(flags)
    for _ in range(shocks):
        m.shocks_in_node.append(ShockRecord(
            context_id="ctx", rule_id=None, scene_type="crossroads",
            option_id="risk", flags=[], sanity_delta=1,
        ))
    return m


def test_pressure_level_critical_when_sanity_very_low() -> None:
    # sanity=1, max=10 → ratio 0.1 → very_low → maps to critical
    entry = build_scene_history_entry(_core(sanity=1), RunMemory(), _node())
    assert entry.pressure_level == "critical"


def test_pressure_level_low_when_sanity_high() -> None:
    # sanity=75, max=100 → ratio 0.75 → high → maps to low
    entry = build_scene_history_entry(_core(sanity=75), RunMemory(), _node())
    assert entry.pressure_level == "low"


# ---------------------------------------------------------------------------
# build_scene_history_entry — resource_trajectory
# ---------------------------------------------------------------------------

def test_trajectory_critical_when_heavy_sanity_loss() -> None:
    entry = build_scene_history_entry(_core(), RunMemory(), _node(sanity_lost=3))
    assert entry.resource_trajectory == "critical"


def test_trajectory_depleting_when_moderate_loss() -> None:
    entry = build_scene_history_entry(_core(), RunMemory(), _node(sanity_lost=2))
    assert entry.resource_trajectory == "depleting"


def test_trajectory_recovering_when_no_loss_and_leniency() -> None:
    run_mem = RunMemory()
    run_mem.narrator_mood.leniency = 2
    entry = build_scene_history_entry(_core(), run_mem, _node(sanity_lost=0))
    assert entry.resource_trajectory == "recovering"


def test_trajectory_stable_otherwise() -> None:
    entry = build_scene_history_entry(_core(), RunMemory(), _node(sanity_lost=1))
    assert entry.resource_trajectory == "stable"


# ---------------------------------------------------------------------------
# build_scene_history_entry — outcome_class
# ---------------------------------------------------------------------------

def test_outcome_turbulent_when_shocks() -> None:
    entry = build_scene_history_entry(_core(), RunMemory(), _node(shocks=1))
    assert entry.outcome_class == "turbulent"


def test_outcome_deepened_when_important_flags() -> None:
    entry = build_scene_history_entry(_core(), RunMemory(), _node(flags=["chose_greedy_option"]))
    assert entry.outcome_class == "deepened"


def test_outcome_stable_when_clean() -> None:
    entry = build_scene_history_entry(_core(), RunMemory(), _node())
    assert entry.outcome_class == "stable"


# ---------------------------------------------------------------------------
# build_scene_history_entry — narrative_thread
# ---------------------------------------------------------------------------

def test_narrative_thread_picks_highest_frequency_theme() -> None:
    run_mem = RunMemory()
    run_mem.theme_counters = {"clarity": 1, "self_preservation": 3, "greed": 2}
    entry = build_scene_history_entry(_core(), run_mem, _node())
    assert entry.narrative_thread == "self_preservation"


def test_narrative_thread_empty_when_no_themes() -> None:
    entry = build_scene_history_entry(_core(), RunMemory(), _node())
    assert entry.narrative_thread == ""


# ---------------------------------------------------------------------------
# build_scene_history_entry — passthrough fields
# ---------------------------------------------------------------------------

def test_entry_waypoint_id_and_depth_match_node_memory() -> None:
    node = WaypointMemory(waypoint_id="archive_floor2", waypoint_type="archive", depth=4)
    entry = build_scene_history_entry(_core(), RunMemory(), node)
    assert entry.waypoint_id == "archive_floor2"
    assert entry.scene_type == "archive"
    assert entry.depth == 4
