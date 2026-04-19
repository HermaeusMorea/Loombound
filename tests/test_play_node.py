"""Tests for _play_node — authored encounter spec path (no LLM / no prefetch)."""

import pytest

from src.t0.memory import CoreStateView, MetaStateView
from src.runtime.session import Run
from src.runtime.play_cli import _play_node
import src.runtime.play_encounter  # noqa: F401 — imported to enable monkeypatching


# ---------------------------------------------------------------------------
# Shared I/O patches (all bound in src.runtime.play_cli namespace)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _silence_io(monkeypatch):
    monkeypatch.setattr("src.runtime.play_cli.choose_index", lambda *_: 0)
    monkeypatch.setattr("src.runtime.play_encounter.choose_index", lambda *_: 0)
    monkeypatch.setattr("src.runtime.play_encounter.pause", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_cli.render_node_header", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_encounter_view", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_choices", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_input_panel", lambda *_: None)
    monkeypatch.setattr("src.runtime.play_encounter.render_result", lambda *_: None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_run() -> Run:
    return Run(
        run_id="r1",
        core_state=CoreStateView(depth=1, act=1, health=10, max_health=10, money=5, sanity=8),
        meta_state=MetaStateView(),
    )


def _authored_asset(context_id: str = "enc1", money_delta: int = 0) -> dict:
    """Valid nested-format encounter payload that passes validate_encounter_asset."""
    return {
        "context": {
            "context_id": context_id,
            "depth": 1,
            "scene_type": "crossroads",
            "resources": {},
            "tags": ["branching_path"],
        },
        "options": [
            {
                "option_id": "go",
                "label": "Press forward",
                "tags": ["safe"],
                "metadata": {"effects": {"health_delta": 0, "money_delta": money_delta, "sanity_delta": 0}},
            }
        ],
    }


def _waypoint_spec(num_encounters: int = 1) -> dict:
    """Saga waypoint spec with authored encounter file references."""
    return {
        "depth": 2,
        "waypoint_type": "crossroads",
        "encounters": [{"file": f"data/enc_{i}.json"} for i in range(num_encounters)],
    }


def _saga() -> dict:
    return {"waypoints": {}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_play_node_returns_waypoint_memory(monkeypatch) -> None:
    monkeypatch.setattr("src.runtime.play_cli.load_json_asset", lambda _p: _authored_asset())
    run = _make_run()
    result = _play_node(run, _saga(), _waypoint_spec(), rules=[], saga_waypoint_id="node1")
    from src.t0.memory.types import WaypointMemory
    assert isinstance(result, WaypointMemory)


def test_play_node_closes_waypoint_and_adds_to_run_history(monkeypatch) -> None:
    monkeypatch.setattr("src.runtime.play_cli.load_json_asset", lambda _p: _authored_asset())
    run = _make_run()
    _play_node(run, _saga(), _waypoint_spec(), rules=[], saga_waypoint_id="node1")
    assert run.current_waypoint is None
    assert len(run.waypoint_history) == 1
    assert run.waypoint_history[0].waypoint_id == "node1:depth_02"


def test_play_node_runs_two_authored_encounters(monkeypatch) -> None:
    call_count = 0

    def _fake_asset(_p):
        nonlocal call_count
        call_count += 1
        return _authored_asset(context_id=f"enc_{call_count}")

    monkeypatch.setattr("src.runtime.play_cli.load_json_asset", _fake_asset)
    run = _make_run()
    memory = _play_node(run, _saga(), _waypoint_spec(num_encounters=2), rules=[], saga_waypoint_id="node1")
    assert len(memory.choices_made) == 2


def test_play_node_updates_run_memory_sanity(monkeypatch) -> None:
    # The single option has sanity_delta=0 and no rule cost → sanity unchanged,
    # but run.memory.sanity accumulates node.sanity_lost_in_node (0) — just check it ran.
    monkeypatch.setattr("src.runtime.play_cli.load_json_asset", lambda _p: _authored_asset())
    run = _make_run()
    _play_node(run, _saga(), _waypoint_spec(), rules=[], saga_waypoint_id="node1")
    # run.memory.sanity starts at 0, node lost 0 → still 0
    assert run.memory.sanity == 0


def test_play_node_node_summary_format(monkeypatch) -> None:
    monkeypatch.setattr("src.runtime.play_cli.load_json_asset", lambda _p: _authored_asset())
    run = _make_run()
    memory = _play_node(run, _saga(), _waypoint_spec(), rules=[], saga_waypoint_id="node1")
    assert memory.node_summary.startswith("crossroads:")
    assert "encounters" in memory.node_summary
    assert "sanity=" in memory.node_summary


def test_play_node_applies_money_effect_via_authored_payload(monkeypatch) -> None:
    monkeypatch.setattr("src.runtime.play_cli.load_json_asset",
                        lambda _p: _authored_asset(money_delta=3))
    run = _make_run()
    assert run.core_state.money == 5
    _play_node(run, _saga(), _waypoint_spec(), rules=[], saga_waypoint_id="node1")
    assert run.core_state.money == 8


def test_play_node_llm_mode_without_prefetch_raises(monkeypatch) -> None:
    spec = {"depth": 1, "waypoint_type": "crossroads", "encounters": 2}  # int → LLM mode
    run = _make_run()
    with pytest.raises(RuntimeError, match="Prefetch unavailable"):
        _play_node(run, _saga(), spec, rules=[], prefetch=None, saga_waypoint_id="node1")
