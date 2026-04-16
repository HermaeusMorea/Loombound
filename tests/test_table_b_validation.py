"""Tests for _validate_table_b_response — structural and content checks."""

from __future__ import annotations

from generate_campaign import _validate_table_b_response


def _valid_arb(node_id: str = "node_a", n_opts: int = 2) -> dict:
    return {
        "node_id": node_id,
        "arbitrations": [
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
    raw = {"nodes": [_valid_arb("node_a", 2)]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert errors == []


def test_multiple_valid_nodes_no_errors():
    raw = {
        "nodes": [
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
    raw = {"nodes": []}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("missing node_id=node_a" in e for e in errors)


def test_wrong_arbitration_count_is_reported():
    node = _valid_arb("node_a")
    node["arbitrations"].append(node["arbitrations"][0].copy())  # now 2
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("node_a" in e and "expected 1" in e for e in errors)


# ---------------------------------------------------------------------------
# Content errors — empty fields
# ---------------------------------------------------------------------------

def test_empty_scene_concept_is_reported():
    node = _valid_arb("node_a")
    node["arbitrations"][0]["scene_concept"] = ""
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("scene_concept is empty" in e for e in errors)


def test_whitespace_only_scene_concept_is_reported():
    node = _valid_arb("node_a")
    node["arbitrations"][0]["scene_concept"] = "   "
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("scene_concept is empty" in e for e in errors)


def test_empty_sanity_axis_is_reported():
    node = _valid_arb("node_a")
    node["arbitrations"][0]["sanity_axis"] = ""
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("sanity_axis is empty" in e for e in errors)


def test_empty_options_list_is_reported():
    node = _valid_arb("node_a")
    node["arbitrations"][0]["options"] = []
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("options list is empty" in e for e in errors)


def test_empty_option_id_is_reported():
    node = _valid_arb("node_a")
    node["arbitrations"][0]["options"][0]["option_id"] = ""
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("option_id is empty" in e for e in errors)


def test_empty_intent_is_reported():
    node = _valid_arb("node_a")
    node["arbitrations"][0]["options"][0]["intent"] = "  "
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert any("intent is empty" in e for e in errors)


# ---------------------------------------------------------------------------
# Multiple simultaneous errors all surface
# ---------------------------------------------------------------------------

def test_multiple_errors_all_reported():
    node = _valid_arb("node_a")
    node["arbitrations"][0]["scene_concept"] = ""
    node["arbitrations"][0]["sanity_axis"] = ""
    node["arbitrations"][0]["options"][0]["intent"] = ""
    raw = {"nodes": [node]}
    errors = _validate_table_b_response(raw, {"node_a": 1})
    assert len(errors) >= 3
