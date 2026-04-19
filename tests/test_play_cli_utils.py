from src.runtime.play_cli import _parse_encounters, _overlay_effects


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
# _overlay_effects
# ---------------------------------------------------------------------------

def _opt(option_id: str, extra_meta: dict | None = None) -> dict:
    meta = dict(extra_meta or {})
    return {"option_id": option_id, "metadata": meta}


def test_overlay_effects_patches_three_stat_keys() -> None:
    payload = {"options": [_opt("a")]}
    result = _overlay_effects(payload, {"a": {"health_delta": -2, "money_delta": 1, "sanity_delta": -1, "toll": ""}})
    eff = result["options"][0]["metadata"]["effects"]
    assert eff["health_delta"] == -2
    assert eff["money_delta"] == 1
    assert eff["sanity_delta"] == -1


def test_overlay_effects_does_not_mutate_original() -> None:
    payload = {"options": [_opt("a")]}
    _overlay_effects(payload, {"a": {"health_delta": -2, "money_delta": 1, "sanity_delta": -1, "toll": ""}})
    assert "effects" not in payload["options"][0].get("metadata", {})


def test_overlay_effects_sets_toll_when_nonempty() -> None:
    payload = {"options": [_opt("a")]}
    result = _overlay_effects(payload, {"a": {"health_delta": 0, "money_delta": 0, "sanity_delta": 0, "toll": "destabilizing"}})
    assert result["options"][0]["toll"] == "destabilizing"


def test_overlay_effects_skips_toll_when_empty_string() -> None:
    payload = {"options": [_opt("a")]}
    result = _overlay_effects(payload, {"a": {"health_delta": 0, "money_delta": 0, "sanity_delta": 0, "toll": ""}})
    assert "toll" not in result["options"][0]


def test_overlay_effects_preserves_existing_metadata_keys() -> None:
    payload = {"options": [_opt("a", {"add_marks": ["cursed"], "effects": {}})]}
    result = _overlay_effects(payload, {"a": {"health_delta": 0, "money_delta": 0, "sanity_delta": -1, "toll": ""}})
    assert result["options"][0]["metadata"]["add_marks"] == ["cursed"]


def test_overlay_effects_unknown_option_id_is_ignored() -> None:
    payload = {"options": [_opt("a")]}
    result = _overlay_effects(payload, {"z": {"health_delta": -99, "money_delta": 0, "sanity_delta": 0, "toll": ""}})
    assert "effects" not in result["options"][0]["metadata"]


def test_overlay_effects_multiple_options_patches_only_matching() -> None:
    payload = {"options": [_opt("a"), _opt("b")]}
    result = _overlay_effects(payload, {"b": {"health_delta": 3, "money_delta": 0, "sanity_delta": 0, "toll": ""}})
    assert "effects" not in result["options"][0]["metadata"]
    assert result["options"][1]["metadata"]["effects"]["health_delta"] == 3
