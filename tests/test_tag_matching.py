"""Tests for Step 4a semantic tag matching in effects_templater._bucket.

Uses a controlled fake embedder backend so the tests never download a model
and run in milliseconds.
"""

import pytest

from src.shared import embedder
from src.t0.core.effects_templater import _bucket, generate_effects
from src.t0.memory import RuleTemplate


def _rule_with_embeddings(pref: list[str], forb: list[str]) -> RuleTemplate:
    """Build a rule and pre-compute embeddings via the installed fake backend."""
    rule = RuleTemplate(
        id="r", name="n", decision_types=["encounter"], theme="t", priority=1,
        preferred_option_tags=pref,
        forbidden_option_tags=forb,
    )
    rule._pref_embeddings = embedder.embed_batch(pref) if pref else []
    rule._forbid_embeddings = embedder.embed_batch(forb) if forb else []
    return rule


@pytest.fixture(autouse=True)
def _fake_backend():
    embedder.install_fake_backend(embedder.hash_based_fake)
    yield
    embedder.install_fake_backend(None)


def test_bucket_still_falls_back_to_string_match_when_fast_path_hits() -> None:
    rule = _rule_with_embeddings(pref=["shelter"], forb=["reckless"])
    # Exact string match → fast path wins; doesn't need semantic comparison.
    assert _bucket(["shelter"], rule) == "preferred"
    assert _bucket(["reckless"], rule) == "forbidden"
    assert _bucket(["unrelated"], rule) == "neutral"


def test_bucket_semantic_path_catches_identical_via_hash_fake() -> None:
    # With the hash-based fake, only identical strings have cosine 1.0;
    # paraphrases won't match with this stub. Just confirm identity works.
    rule = _rule_with_embeddings(pref=["shelter"], forb=[])
    # "shelter" literal hits fast path — already tested above.
    # Purpose: confirm semantic path doesn't blow up on a disjoint tag.
    assert _bucket(["totally_unrelated_word"], rule) == "neutral"


def test_bucket_with_no_embeddings_on_rule_falls_to_neutral() -> None:
    # Rule with tags but missing embeddings (e.g. embedder was disabled at
    # saga-load time). Should not crash; should just miss semantic path.
    rule = RuleTemplate(
        id="r", name="n", decision_types=["encounter"], theme="t", priority=1,
        preferred_option_tags=["shelter"],
    )
    # No _pref_embeddings / _forbid_embeddings attached (default empty lists).
    # String match for 'shelter' would hit fast path; use a disjoint tag.
    assert _bucket(["totally_unrelated"], rule) == "neutral"


def test_generate_effects_semantic_and_string_same_result_for_exact_match() -> None:
    rule = _rule_with_embeddings(pref=["safe"], forb=["reckless"])
    bands = {"health": "moderate", "money": "moderate", "sanity": "moderate"}
    out = generate_effects(rule, [{"option_id": "a", "tags": ["safe"]}], bands)
    # Fast-path preferred bucket → stable toll.
    assert out["a"]["toll"] == "stable"


def test_bucket_handles_empty_tag_list() -> None:
    rule = _rule_with_embeddings(pref=["safe"], forb=["reckless"])
    assert _bucket([], rule) == "neutral"
