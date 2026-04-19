from src.t0.memory import Encounter
from src.t0.core.signals import build_signals


def _enc(scene_type: str = "crossroads", tags: list[str] | None = None,
         options: list[dict] | None = None, resources: dict | None = None) -> Encounter:
    return Encounter.from_dict(
        {
            "context_id": "ctx",
            "scene_type": scene_type,
            "depth": 1,
            "resources": resources or {},
            "tags": tags or [],
            "options": options or [],
        },
        owner_kind="node",
        owner_id="wp1",
    )


# ---------------------------------------------------------------------------
# scene_type and context_tags pass-through
# ---------------------------------------------------------------------------

def test_scene_type_reflected() -> None:
    sig = build_signals(_enc(scene_type="archive"))
    assert sig["scene_type"] == "archive"


def test_context_tags_as_set() -> None:
    sig = build_signals(_enc(tags=["branching_path", "omens"]))
    assert sig["context_tags"] == {"branching_path", "omens"}


# ---------------------------------------------------------------------------
# option tag detection
# ---------------------------------------------------------------------------

def test_has_safe_option_true() -> None:
    opts = [{"option_id": "a", "label": "x", "tags": ["safe"], "metadata": {}}]
    sig = build_signals(_enc(options=opts))
    assert sig["has_safe_option"] is True


def test_has_safe_option_false() -> None:
    opts = [{"option_id": "a", "label": "x", "tags": ["volatile"], "metadata": {}}]
    sig = build_signals(_enc(options=opts))
    assert sig["has_safe_option"] is False


def test_has_greedy_option_true() -> None:
    opts = [{"option_id": "a", "label": "x", "tags": ["greedy"], "metadata": {}}]
    sig = build_signals(_enc(options=opts))
    assert sig["has_greedy_option"] is True


def test_has_volatile_option_via_occult_tag() -> None:
    opts = [{"option_id": "a", "label": "x", "tags": ["occult"], "metadata": {}}]
    sig = build_signals(_enc(options=opts))
    assert sig["has_volatile_option"] is True


# ---------------------------------------------------------------------------
# resource band thresholds
# ---------------------------------------------------------------------------

def test_low_health_at_boundary() -> None:
    assert build_signals(_enc(resources={"health": 4}))["low_health"] is True
    assert build_signals(_enc(resources={"health": 5}))["low_health"] is False


def test_high_health_at_boundary() -> None:
    assert build_signals(_enc(resources={"health": 8}))["high_health"] is True
    assert build_signals(_enc(resources={"health": 7}))["high_health"] is False


def test_low_money_at_boundary() -> None:
    assert build_signals(_enc(resources={"money": 3}))["low_money"] is True
    assert build_signals(_enc(resources={"money": 4}))["low_money"] is False


def test_high_money_at_boundary() -> None:
    assert build_signals(_enc(resources={"money": 9}))["high_money"] is True
    assert build_signals(_enc(resources={"money": 8}))["high_money"] is False


def test_low_sanity_at_boundary() -> None:
    assert build_signals(_enc(resources={"sanity": 4}))["low_sanity"] is True
    assert build_signals(_enc(resources={"sanity": 5}))["low_sanity"] is False


def test_high_sanity_at_boundary() -> None:
    assert build_signals(_enc(resources={"sanity": 8}))["high_sanity"] is True
    assert build_signals(_enc(resources={"sanity": 7}))["high_sanity"] is False


def test_none_resource_treated_as_zero() -> None:
    sig = build_signals(_enc(resources={}))
    assert sig["low_health"] is True   # 0 <= 4
    assert sig["low_money"] is True
    assert sig["low_sanity"] is True
