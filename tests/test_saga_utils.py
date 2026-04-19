import io
import pytest

from src.t0.memory import CoreStateView, MetaStateView
from src.runtime.play_runtime import make_run, choose_index, resolve_asset_path, sync_encounter_resources
from src.runtime.session import Run, Encounter


# ---------------------------------------------------------------------------
# make_run
# ---------------------------------------------------------------------------

def _minimal_saga(**overrides) -> dict:
    base = {
        "saga_id": "test_saga",
        "initial_core_state": {"depth": 1, "health": 10, "max_health": 10, "money": 5, "sanity": 8},
    }
    base.update(overrides)
    return base


def test_make_run_sets_run_id() -> None:
    run = make_run(_minimal_saga())
    assert run.run_id == "test_saga"


def test_make_run_maps_core_state_fields() -> None:
    run = make_run(_minimal_saga())
    assert run.core_state.health == 10
    assert run.core_state.money == 5
    assert run.core_state.sanity == 8
    assert run.core_state.depth == 1


def test_make_run_syncs_meta_state_sanity() -> None:
    run = make_run(_minimal_saga())
    assert run.meta_state.sanity == 8


def test_make_run_loads_initial_marks() -> None:
    saga = _minimal_saga()
    saga["initial_meta_state"] = {"active_marks": ["cursed", "exiled"]}
    run = make_run(saga)
    assert run.meta_state.active_marks == ["cursed", "exiled"]


def test_make_run_missing_optional_fields_use_defaults() -> None:
    run = make_run({"saga_id": "s", "initial_core_state": {}})
    assert run.core_state.depth == 1
    assert run.core_state.act == 1
    assert run.core_state.health is None


# ---------------------------------------------------------------------------
# resolve_asset_path
# ---------------------------------------------------------------------------

def test_resolve_asset_path_relative_prepends_repo_root() -> None:
    p = resolve_asset_path("data/sagas/test.json")
    assert p.is_absolute()
    assert str(p).endswith("data/sagas/test.json")


def test_resolve_asset_path_absolute_unchanged() -> None:
    p = resolve_asset_path("/tmp/test.json")
    assert str(p) == "/tmp/test.json"


# ---------------------------------------------------------------------------
# choose_index
# ---------------------------------------------------------------------------

def test_choose_index_valid_input(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "2")
    assert choose_index("> ", 3) == 1   # "2" → 0-based index 1


def test_choose_index_first_option(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "1")
    assert choose_index("> ", 3) == 0


def test_choose_index_last_option(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "3")
    assert choose_index("> ", 3) == 2


def test_choose_index_out_of_range_then_valid(monkeypatch) -> None:
    responses = iter(["5", "0", "2"])   # 5 out of range, 0 invalid, 2 valid
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    monkeypatch.setattr("builtins.print", lambda *_: None)
    assert choose_index("> ", 3) == 1


def test_choose_index_quit_raises_keyboard_interrupt(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "q")
    with pytest.raises(KeyboardInterrupt):
        choose_index("> ", 3)


def test_choose_index_zero_count_raises() -> None:
    with pytest.raises(ValueError):
        choose_index("> ", 0)


# ---------------------------------------------------------------------------
# sync_encounter_resources
# ---------------------------------------------------------------------------

def _run_with_stats(health=7, money=4, sanity=6) -> Run:
    return Run(
        run_id="r",
        core_state=CoreStateView(depth=1, health=health, max_health=10, money=money, sanity=sanity),
        meta_state=MetaStateView(),
    )


def _enc() -> Encounter:
    return Encounter.from_dict(
        {"context_id": "ctx", "scene_type": "crossroads", "depth": 1,
         "resources": {"health": 0, "money": 0, "sanity": 0}, "options": []},
        owner_kind="node", owner_id="wp1",
    )


def test_sync_encounter_resources_copies_run_stats() -> None:
    run = _run_with_stats(health=7, money=4, sanity=6)
    enc = _enc()
    sync_encounter_resources(run, enc)
    assert enc.context.resources["health"] == 7
    assert enc.context.resources["money"] == 4
    assert enc.context.resources["sanity"] == 6


def test_sync_encounter_resources_updates_core_state_view() -> None:
    run = _run_with_stats(health=7, money=4, sanity=6)
    enc = _enc()
    sync_encounter_resources(run, enc)
    assert enc.context.core_state_view.health == 7
    assert enc.context.core_state_view.sanity == 6
