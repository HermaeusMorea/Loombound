from src.t0.memory import (
    CoreStateView, MetaStateView, EncounterResult, OptionResult,
    NarrationBlock, WaypointSummary,
)
from src.runtime.session import Encounter, Waypoint, Run


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _core() -> CoreStateView:
    return CoreStateView(depth=1, act=1, health=10, max_health=10, money=3, sanity=8)


def _meta() -> MetaStateView:
    return MetaStateView()


def _enc_payload(scene_type: str = "crossroads") -> dict:
    return {
        "context_id": "ctx_test",
        "scene_type": scene_type,
        "depth": 1,
        "resources": {},
        "options": [
            {"option_id": "a", "label": "Go left", "tags": [], "metadata": {}},
            {"option_id": "b", "label": "Go right", "tags": [], "metadata": {}},
        ],
    }


def _result() -> EncounterResult:
    opt = OptionResult(option_id="a", label="Go left", toll="stable", reasons=[], sanity_cost=0)
    return EncounterResult(
        selected_rule_id=None,
        matched_rule_ids=[],
        option_results=[opt],
        sanity_delta=0,
    )


# ---------------------------------------------------------------------------
# Encounter
# ---------------------------------------------------------------------------

def test_encounter_from_dict_parses_options() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    assert len(enc.options) == 2
    assert enc.options[0]["option_id"] == "a"


def test_encounter_select_option_records_choice() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    enc.select_option("b")
    assert enc.selected_option_id == "b"


def test_encounter_select_unknown_option_raises() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    try:
        enc.select_option("zzz")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_encounter_upsert_option_inserts_new() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    enc.upsert_option({"option_id": "c", "label": "Third path", "tags": [], "metadata": {}})
    assert len(enc.options) == 3
    assert enc.get_option("c") is not None


def test_encounter_upsert_option_replaces_existing() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    enc.upsert_option({"option_id": "a", "label": "Updated left", "tags": [], "metadata": {}})
    assert len(enc.options) == 2
    assert enc.get_option("a")["label"] == "Updated left"


def test_encounter_remove_option_clears_selection_if_selected() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    enc.select_option("a")
    enc.remove_option("a")
    assert enc.selected_option_id is None
    assert enc.get_option("a") is None


def test_encounter_set_result_sets_evaluated_status() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    enc.set_result(_result())
    assert enc.status == "evaluated"
    assert enc.result is not None


def test_encounter_mark_applied_sets_applied_status() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    enc.set_result(_result())
    enc.mark_applied()
    assert enc.status == "applied"


def test_encounter_load_from_dict_resets_status() -> None:
    enc = Encounter.from_dict(_enc_payload(), owner_kind="node", owner_id="wp1")
    enc.set_result(_result())
    enc.mark_applied()
    enc.load_from_dict(_enc_payload())
    assert enc.status == "pending"
    assert enc.result is None
    assert enc.selected_option_id is None


# ---------------------------------------------------------------------------
# Waypoint
# ---------------------------------------------------------------------------

def test_waypoint_post_init_creates_memory_and_rule_state() -> None:
    wp = Waypoint(
        waypoint_id="wp1", waypoint_type="crossroads", depth=1,
        parent_run_id="run1", entered_core_state=_core(), entered_meta_state=_meta(),
    )
    assert wp.memory is not None
    assert wp.rule_state is not None


def test_waypoint_initialize_encounter_creates_shell() -> None:
    wp = Waypoint(
        waypoint_id="wp1", waypoint_type="crossroads", depth=1,
        parent_run_id="run1", entered_core_state=_core(), entered_meta_state=_meta(),
    )
    enc = wp.initialize_encounter()
    assert enc is not None
    assert wp.current_encounter is enc


def test_waypoint_close_current_encounter_archives_to_history() -> None:
    wp = Waypoint(
        waypoint_id="wp1", waypoint_type="crossroads", depth=1,
        parent_run_id="run1", entered_core_state=_core(), entered_meta_state=_meta(),
    )
    wp.initialize_encounter()
    wp.close_current_encounter()
    assert wp.current_encounter is None
    assert len(wp.encounter_history) == 1


def test_waypoint_build_summary_reflects_depth_and_type() -> None:
    wp = Waypoint(
        waypoint_id="wp42", waypoint_type="archive", depth=3,
        parent_run_id="run1", entered_core_state=_core(), entered_meta_state=_meta(),
    )
    summary = wp.build_summary()
    assert summary.waypoint_id == "wp42"
    assert summary.waypoint_type == "archive"
    assert summary.depth == 3


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def test_run_post_init_creates_memory_and_rule_system() -> None:
    run = Run(run_id="r1", core_state=_core(), meta_state=_meta())
    assert run.memory is not None
    assert run.rule_system is not None


def test_run_start_waypoint_sets_current_waypoint() -> None:
    run = Run(run_id="r1", core_state=_core(), meta_state=_meta())
    wp = run.start_waypoint("wp1", "crossroads", depth=1)
    assert run.current_waypoint is wp
    assert wp.parent_run_id == "r1"


def test_run_close_current_waypoint_stores_summary() -> None:
    run = Run(run_id="r1", core_state=_core(), meta_state=_meta())
    run.start_waypoint("wp1", "crossroads", depth=1)
    summary = WaypointSummary(waypoint_id="wp1", waypoint_type="crossroads", depth=1)
    run.close_current_waypoint(summary=summary)
    assert run.current_waypoint is None
    assert len(run.waypoint_history) == 1
    assert run.waypoint_history[0].waypoint_id == "wp1"


def test_run_waypoint_history_accumulates() -> None:
    run = Run(run_id="r1", core_state=_core(), meta_state=_meta())
    for i in range(3):
        run.start_waypoint(f"wp{i}", "crossroads", depth=i + 1)
        s = WaypointSummary(waypoint_id=f"wp{i}", waypoint_type="crossroads", depth=i + 1)
        run.close_current_waypoint(summary=s)
    assert len(run.waypoint_history) == 3
