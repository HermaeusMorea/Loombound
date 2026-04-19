"""Tests for CachedContextBundle and build_m2_context."""

from src.t2.core.m2_context import CachedContextBundle, build_m2_context


def test_global_block_contains_catalog():
    bundle = build_m2_context(arc_state_catalog_json="[1,2,3]", quasi_state="state")
    assert len(bundle.global_blocks) == 1
    assert "Arc-state catalog" in bundle.global_blocks[0]["text"]
    assert bundle.global_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_saga_blocks_empty_when_no_option_index():
    bundle = build_m2_context(arc_state_catalog_json="{}", quasi_state="state")
    assert bundle.saga_blocks == []


def test_saga_block_includes_option_index():
    bundle = build_m2_context(
        arc_state_catalog_json="{}",
        scene_option_index_json="[opts]",
        quasi_state="state",
    )
    assert len(bundle.saga_blocks) == 1
    assert "Scene option index" in bundle.saga_blocks[0]["text"]
    assert bundle.saga_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_saga_block_appends_rules_and_lexicon():
    bundle = build_m2_context(
        arc_state_catalog_json="{}",
        scene_option_index_json="[opts]",
        rules_json="[rules]",
        toll_lexicon_json="[tolls]",
        quasi_state="state",
    )
    text = bundle.saga_blocks[0]["text"]
    assert "Saga rules" in text
    assert "Toll lexicon" in text


def test_dynamic_block_contains_quasi_state_and_arb_hint():
    bundle = build_m2_context(
        arc_state_catalog_json="{}",
        quasi_state="current state",
        arb_hint="\n\nAssign effects for: waypoint_id=wp1, arb_index=0",
    )
    assert len(bundle.dynamic_blocks) == 1
    text = bundle.dynamic_blocks[0]["text"]
    assert "current state" in text
    assert "Assign effects" in text
    assert "cache_control" not in bundle.dynamic_blocks[0]


def test_to_user_content_flattens_all_tiers():
    bundle = build_m2_context(
        arc_state_catalog_json="{}",
        scene_option_index_json="[opts]",
        quasi_state="state",
    )
    content = bundle.to_user_content()
    assert len(content) == 3   # global + saga + dynamic
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert content[1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in content[2]
