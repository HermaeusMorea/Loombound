"""Tests for _validate_t1_cache_table_response — structural and content checks."""

from __future__ import annotations

from gen_t1_cache_table import _validate_t1_cache_table_response as _validate_table_b_response


def _valid_arb(waypoint_id: str = "node_a", n_opts: int = 2) -> dict:
    return {
        "waypoint_id": waypoint_id,
        "encounters": [
            {
                "scene_concept": "A flooded market stall",
                "sanity_axis": "Trust vs suspicion",
                "options": [
                    {"option_id": f"opt_{i}", "intent": f"Do thing {i}"}
                    for i in range(n_opts)
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_response_returns_no_errors():
    raw = {"waypoints": [_valid_arb("node_a", 2)]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert errors == []


def test_multiple_valid_nodes_no_errors():
    raw = {
        "waypoints": [
            _valid_arb("node_a"),
            _valid_arb("node_b"),
        ]
    }
    errors = _validate_table_b_response(raw, {"node_a": 1, "node_b": 1})
    assert errors == []


# ---------------------------------------------------------------------------
# Structural errors
# ---------------------------------------------------------------------------

def test_missing_node_is_reported():
    raw = {"waypoints": []}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("missing waypoint_id=node_a" in e for e in errors)


def test_wrong_encounter_count_is_reported():
    node = _valid_arb("node_a")
    node["encounters"].append(node["encounters"][0].copy())  # now 2
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("node_a" in e and "expected 1" in e for e in errors)


# ---------------------------------------------------------------------------
# Content errors — empty fields
# ---------------------------------------------------------------------------

def test_empty_scene_concept_is_reported():
    node = _valid_arb("node_a")
    node["encounters"][0]["scene_concept"] = ""
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("scene_concept is empty" in e for e in errors)


def test_whitespace_only_scene_concept_is_reported():
    node = _valid_arb("node_a")
    node["encounters"][0]["scene_concept"] = "   "
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("scene_concept is empty" in e for e in errors)


def test_empty_sanity_axis_is_reported():
    node = _valid_arb("node_a")
    node["encounters"][0]["sanity_axis"] = ""
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("sanity_axis is empty" in e for e in errors)


def test_empty_options_list_is_reported():
    node = _valid_arb("node_a")
    node["encounters"][0]["options"] = []
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("options list is empty" in e for e in errors)


def test_empty_option_id_is_reported():
    node = _valid_arb("node_a")
    node["encounters"][0]["options"][0]["option_id"] = ""
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("option_id is empty" in e for e in errors)


def test_empty_intent_is_reported():
    node = _valid_arb("node_a")
    node["encounters"][0]["options"][0]["intent"] = "  "
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("intent is empty" in e for e in errors)


# ---------------------------------------------------------------------------
# Multiple simultaneous errors all surface
# ---------------------------------------------------------------------------

def test_multiple_errors_all_reported():
    node = _valid_arb("node_a")
    node["encounters"][0]["scene_concept"] = ""
    node["encounters"][0]["sanity_axis"] = ""
    node["encounters"][0]["options"][0]["intent"] = ""
    raw = {"waypoints": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert len(errors) >= 3
