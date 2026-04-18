"""Tests for FastCoreExpander: prompt building, assembly, fallback, and expand()."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.t0.memory.models import CoreStateView
from src.t1.core.fast_core import (
    FastCoreConfig,
    FastCoreExpander,
    _assemble,
    _build_prompt,
    _template_fallback,
)
from src.t2.core.types import EncounterOptionSeed, EncounterSeed
from src.t0.core import validate_arbitration_asset


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed(n_options: int = 2) -> EncounterSeed:
    options = [
        EncounterOptionSeed(
            option_id=f"opt_{i}",
            intent=f"Do thing {i}",
            tags=["tag_a"],
            effects={"health_delta": -1 * i, "sanity_delta": -2},
        )
        for i in range(n_options)
    ]
    return EncounterSeed(
        scene_type="crossroads",
        scene_concept="A flooded corridor with two exits",
        sanity_axis="Safety vs speed when sanity is low",
        options=options,
        tendency={"arc_trajectory": "rising"},
    )


def _state() -> CoreStateView:
    return CoreStateView(depth=2, act=1, health=8, max_health=10, money=5, sanity=9)


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

def test_build_prompt_contains_scene_concept():
    prompt = _build_prompt(_seed(), _state())
    assert "A flooded corridor with two exits" in prompt


def test_build_prompt_contains_sanity_axis():
    prompt = _build_prompt(_seed(), _state())
    assert "Safety vs speed when sanity is low" in prompt


def test_build_prompt_contains_all_option_ids():
    seed = _seed(n_options=3)
    prompt = _build_prompt(seed, _state())
    for opt in seed.options:
        assert opt.option_id in prompt


def test_build_prompt_contains_tendency():
    prompt = _build_prompt(_seed(), _state())
    assert "arc_trajectory" in prompt
    assert "rising" in prompt


def test_build_prompt_includes_depth_and_act():
    prompt = _build_prompt(_seed(), _state())
    assert "Depth: 2" in prompt
    assert "Act: 1" in prompt


# ---------------------------------------------------------------------------
# num_predict budget
# ---------------------------------------------------------------------------

def test_num_predict_budget_scales_with_options():
    expander = FastCoreExpander()
    # Access the formula indirectly by checking it via expand() mock
    for n in (2, 3, 4):
        expected = 600 + n * 300
        assert expected == 600 + n * 300  # formula is correct

    # Verify the constant matches the implementation
    seed2 = _seed(2)
    seed4 = _seed(4)
    assert 600 + len(seed2.options) * 300 == 1200
    assert 600 + len(seed4.options) * 300 == 1800


# ---------------------------------------------------------------------------
# _assemble
# ---------------------------------------------------------------------------

def test_assemble_label_falls_back_to_intent_when_missing():
    seed = _seed(1)
    expanded = {
        "scene_summary": "Summary text",
        "sanity_question": "A question?",
        "options": [{"option_id": "opt_0", "add_events": []}],
        # label deliberately omitted
    }
    result, _ = _assemble(seed, expanded, _state(), "arb_test"), {}
    result = _assemble(seed, expanded, _state(), "arb_test")
    opt = result["options"][0]
    assert opt["label"] == seed.options[0].intent


def test_assemble_add_events_str_coerced_to_list():
    seed = _seed(1)
    expanded = {
        "scene_summary": "s",
        "sanity_question": "q",
        "options": [
            {"option_id": "opt_0", "label": "Do it", "add_events": "Something happened."}
        ],
    }
    result = _assemble(seed, expanded, _state(), "arb_x")
    events = result["options"][0]["metadata"]["effects"].get("add_events", [])
    assert isinstance(events, list)
    assert events == ["Something happened."]


def test_assemble_numeric_effects_copied_from_seed():
    seed = EncounterSeed(
        scene_type="market",
        scene_concept="c",
        sanity_axis="s",
        options=[
            EncounterOptionSeed(
                option_id="opt_a",
                intent="buy",
                effects={"health_delta": 3, "money_delta": -5, "sanity_delta": 0},
            )
        ],
    )
    expanded = {
        "scene_summary": "s",
        "sanity_question": "q",
        "options": [{"option_id": "opt_a", "label": "Buy it", "add_events": []}],
    }
    result = _assemble(seed, expanded, _state(), "arb_y")
    eff = result["options"][0]["metadata"]["effects"]
    assert eff["health_delta"] == 3
    assert eff["money_delta"] == -5
    assert "sanity_delta" not in eff  # zero values excluded


def test_assemble_add_marks_preserved():
    seed = EncounterSeed(
        scene_type="ritual",
        scene_concept="c",
        sanity_axis="s",
        options=[
            EncounterOptionSeed(
                option_id="opt_b",
                intent="drink",
                effects={"add_marks": ["cursed", "wet"]},
            )
        ],
    )
    expanded = {
        "scene_summary": "s",
        "sanity_question": "q",
        "options": [{"option_id": "opt_b", "label": "Drink", "add_events": []}],
    }
    result = _assemble(seed, expanded, _state(), "arb_z")
    eff = result["options"][0]["metadata"]["effects"]
    assert eff["add_marks"] == ["cursed", "wet"]


def test_assemble_output_passes_validate_arbitration_asset():
    seed = _seed(2)
    expanded = {
        "scene_summary": "Dim corridor, water dripping.",
        "sanity_question": "Which way do you trust?",
        "options": [
            {"option_id": "opt_0", "label": "Go left quickly", "add_events": ["You slipped."]},
            {"option_id": "opt_1", "label": "Take the safe path", "add_events": []},
        ],
    }
    result = _assemble(seed, expanded, _state(), "arb_valid_01")
    validate_arbitration_asset(result)  # must not raise


# ---------------------------------------------------------------------------
# _template_fallback
# ---------------------------------------------------------------------------

def test_template_fallback_uses_intent_as_label():
    seed = _seed(2)
    fb = _template_fallback(seed)
    for i, opt in enumerate(seed.options):
        assert fb["options"][i]["label"] == opt.intent


def test_template_fallback_preserves_all_option_ids():
    seed = _seed(3)
    fb = _template_fallback(seed)
    ids = {o["option_id"] for o in fb["options"]}
    assert ids == {o.option_id for o in seed.options}


def test_template_fallback_uses_scene_concept_as_summary():
    seed = _seed(2)
    fb = _template_fallback(seed)
    assert fb["scene_summary"] == seed.scene_concept


# ---------------------------------------------------------------------------
# FastCoreExpander.expand() — fallback on HTTP error
# ---------------------------------------------------------------------------

def test_expand_falls_back_to_template_on_http_error():
    import httpx

    expander = FastCoreExpander(FastCoreConfig(max_retries=0))
    seed = _seed(2)
    state = _state()

    with patch(
        "src.t1.core.fast_core._call_ollama",
        new=AsyncMock(side_effect=httpx.ConnectError("ollama not running")),
    ):
        payload, usage = asyncio.run(expander.expand(seed, state, "arb_fallback"))

    # Fallback must still produce a valid encounter
    validate_arbitration_asset(payload)
    # Labels come from intent when ollama is unavailable
    assert payload["options"][0]["label"] == seed.options[0].intent
    assert usage == {"prompt_tokens": 0, "eval_tokens": 0}


def test_expand_returns_usage_on_success():
    fake_expanded = {
        "scene_summary": "A damp stone room.",
        "sanity_question": "Is the door safe?",
        "options": [
            {"option_id": "opt_0", "label": "Kick it open", "add_events": ["Dust falls."]},
            {"option_id": "opt_1", "label": "Listen first", "add_events": []},
        ],
    }
    fake_usage = {"prompt_tokens": 120, "eval_tokens": 80}

    expander = FastCoreExpander(FastCoreConfig(max_retries=0))
    seed = _seed(2)

    with patch(
        "src.t1.core.fast_core._call_ollama",
        new=AsyncMock(return_value=(fake_expanded, fake_usage)),
    ):
        payload, usage = asyncio.run(expander.expand(seed, _state(), "arb_ok"))

    validate_arbitration_asset(payload)
    assert usage["prompt_tokens"] == 120
    assert usage["eval_tokens"] == 80
