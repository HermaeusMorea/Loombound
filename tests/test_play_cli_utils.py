from src.runtime.play_cli import _parse_encounters
from src.t0.core.effects_templater import generate_effects
from src.t0.memory import RuleTemplate


# ---------------------------------------------------------------------------
# _parse_encounters
# ---------------------------------------------------------------------------

def test_parse_encounters_int_returns_llm_count() -> None:
    assert _parse_encounters({"encounters": 3}) == (3, [])


def test_parse_encounters_list_returns_authored_specs() -> None:
    specs = [{"file": "a.json"}, {"file": "b.json"}]
    assert _parse_encounters({"encounters": specs}) == (0, specs)


def test_parse_encounters_empty_list_returns_zero_empty() -> None:
    assert _parse_encounters({"encounters": []}) == (0, [])


def test_parse_encounters_missing_key_returns_zero_empty() -> None:
    assert _parse_encounters({}) == (0, [])


# ---------------------------------------------------------------------------
# effects_templater.generate_effects
# ---------------------------------------------------------------------------

def _rule(**overrides) -> RuleTemplate:
    base = dict(
        id="r1", name="n", decision_types=["encounter"], theme="t", priority=1,
        preferred_option_tags=["safe"], forbidden_option_tags=["reckless"],
    )
    base.update(overrides)
    return RuleTemplate(**base)


def _moderate_bands() -> dict[str, str]:
    return {"health": "moderate", "money": "moderate", "sanity": "moderate"}


def test_generate_effects_buckets_by_option_tags() -> None:
    rule = _rule()
    options = [
        {"option_id": "a", "tags": ["safe"]},      # preferred
        {"option_id": "b", "tags": ["reckless"]},  # forbidden
        {"option_id": "c", "tags": ["mystery"]},   # neutral
    ]
    out = generate_effects(rule, options, _moderate_bands())
    assert out["a"]["toll"] == "stable"
    assert out["b"]["toll"] == "destabilizing"
    assert out["c"]["toll"] == "stable"


def test_generate_effects_returns_toll_and_three_deltas() -> None:
    rule = _rule()
    options = [{"option_id": "a", "tags": ["safe"]}]
    out = generate_effects(rule, options, _moderate_bands())
    eff = out["a"]
    assert set(eff.keys()) == {"health_delta", "money_delta", "sanity_delta", "toll"}
    assert isinstance(eff["health_delta"], int)


def test_generate_effects_clamps_to_config_bounds() -> None:
    rule = _rule()
    rule.effects_template = {
        "forbidden": {"toll": "destabilizing", "h": [-50, -30], "m": [-40, -20], "s": [-25, -15]},
    }
    out = generate_effects(
        rule,
        [{"option_id": "x", "tags": ["reckless"]}],
        _moderate_bands(),
    )
    assert out["x"]["health_delta"] == -15  # HEALTH_DELTA_MIN
    assert out["x"]["money_delta"] == -15   # MONEY_DELTA_MIN
    assert out["x"]["sanity_delta"] == -10  # SANITY_DELTA_MIN


def test_generate_effects_no_rule_uses_neutral_bucket() -> None:
    out = generate_effects(None, [{"option_id": "a", "tags": ["anything"]}], _moderate_bands())
    assert out["a"]["toll"] == "stable"


def test_generate_effects_unknown_band_uses_default_position() -> None:
    # Unknown band defaults to moderate (pos 0.5); expect a mid-range pick.
    # Default forbidden h ratio is [-0.12, -0.04] → at max_health=100 that's
    # [-12, -4]. Just assert the value is in that range.
    rule = _rule()
    out = generate_effects(rule, [{"option_id": "a", "tags": ["reckless"]}],
                           {"health": "bogus", "money": "bogus", "sanity": "bogus"})
    assert -12 <= out["a"]["health_delta"] <= -4


def test_generate_effects_forbidden_takes_precedence_over_preferred() -> None:
    rule = _rule()
    # Option has both tags; forbidden must win.
    options = [{"option_id": "a", "tags": ["safe", "reckless"]}]
    out = generate_effects(rule, options, _moderate_bands())
    assert out["a"]["toll"] == "destabilizing"


def test_generate_effects_band_low_is_more_lenient() -> None:
    rule = _rule()
    low = generate_effects(rule, [{"option_id": "x", "tags": ["reckless"]}],
                           {"health": "very_low", "money": "moderate", "sanity": "moderate"})
    high = generate_effects(rule, [{"option_id": "x", "tags": ["reckless"]}],
                            {"health": "very_high", "money": "moderate", "sanity": "moderate"})
    # low health band should lose less blood than high health band
    assert low["x"]["health_delta"] > high["x"]["health_delta"]


def test_default_neutral_bucket_produces_nonzero_cost() -> None:
    """Options that match neither preferred nor forbidden should still feel a toll."""
    rule = _rule()
    out = generate_effects(
        rule,
        [{"option_id": "n", "tags": ["unrelated"]}],
        {"health": "high", "money": "high", "sanity": "high"},
    )
    eff = out["n"]
    # At least one of h/m/s should be non-zero so the player sees a consequence.
    assert (eff["health_delta"] != 0) or (eff["money_delta"] != 0) or (eff["sanity_delta"] != 0)
    # toll stays 'stable' so enforcement doesn't double-charge sanity_penalty.
    assert eff["toll"] == "stable"
