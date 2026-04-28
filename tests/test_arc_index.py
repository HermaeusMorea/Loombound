"""Tests for Step 4b: ArcEmbeddingIndex + cache-hit gate in ArcStateTracker."""

import json
import pytest

from src.shared import embedder
from src.t2.core.arc_index import (
    ArcEmbeddingIndex,
    ArcMatch,
    HIGH_MATCH_THRESHOLD,
    LOW_MATCH_THRESHOLD,
)


@pytest.fixture(autouse=True)
def _fake_backend():
    embedder.install_fake_backend(embedder.hash_based_fake)
    yield
    embedder.install_fake_backend(None)


def _sample_entries():
    return [
        {"entry_id": 0, "arc_trajectory": "rising",   "world_pressure": "low",
         "narrative_pacing": "slow",    "pending_intent": "exploration"},
        {"entry_id": 1, "arc_trajectory": "climax",   "world_pressure": "critical",
         "narrative_pacing": "sprint",  "pending_intent": "confrontation"},
        {"entry_id": 2, "arc_trajectory": "plateau",  "world_pressure": "moderate",
         "narrative_pacing": "steady",  "pending_intent": "recovery"},
    ]


def test_index_construction_succeeds_with_fake_backend() -> None:
    idx = ArcEmbeddingIndex(_sample_entries())
    assert idx.is_enabled() is True


def test_index_disabled_without_embedder(monkeypatch) -> None:
    # Override the fake backend fixture inside this test.
    embedder.install_fake_backend(None)
    monkeypatch.setenv("LOOMBOUND_EMBEDDER_DISABLED", "1")
    idx = ArcEmbeddingIndex(_sample_entries())
    assert idx.is_enabled() is False
    assert idx.lookup("whatever") is None


def test_lookup_returns_arc_match_and_entry_id() -> None:
    idx = ArcEmbeddingIndex(_sample_entries())
    # Query that is string-identical to entry 0's generated description → cosine 1.0.
    # Reuse the same helper used internally so this test keeps working if
    # _describe_entry's prose is reworded.
    from src.t2.core.arc_index import _describe_entry
    desc_0 = _describe_entry(_sample_entries()[0])
    match = idx.lookup(desc_0)
    assert isinstance(match, ArcMatch)
    assert match.entry_id == 0
    assert match.score >= HIGH_MATCH_THRESHOLD
    assert match.source == "cache_hit"


def test_lookup_anomaly_for_completely_unrelated_query() -> None:
    idx = ArcEmbeddingIndex(_sample_entries())
    # Totally unrelated string → hash-based fake gives small random cosine
    match = idx.lookup("this string has nothing to do with arcs whatsoever")
    assert isinstance(match, ArcMatch)
    # Either ambiguous or anomaly — with hash-based fake, typically < low.
    assert match.source in ("ambiguous", "anomaly")


def test_from_json_handles_list_and_dict_shapes() -> None:
    list_json = json.dumps(_sample_entries())
    dict_json = json.dumps({"entries": _sample_entries()})
    empty_json = "[]"

    idx_list = ArcEmbeddingIndex.from_json(list_json)
    idx_dict = ArcEmbeddingIndex.from_json(dict_json)
    idx_empty = ArcEmbeddingIndex.from_json(empty_json)

    assert idx_list.is_enabled() is True
    assert idx_dict.is_enabled() is True
    assert idx_empty.is_enabled() is False


def test_from_json_handles_malformed() -> None:
    idx = ArcEmbeddingIndex.from_json("{not json")
    assert idx.is_enabled() is False


# ---------------------------------------------------------------------------
# ArcStateTracker cache-hit gate behaviour (integration with the fake backend)
# ---------------------------------------------------------------------------

from src.t2.core.arc_state import ArcStateTracker


class _FakeEngine:
    """Records whether classify was called."""

    def __init__(self) -> None:
        self.call_count = 0

    async def classify(self, *args, **kwargs):
        self.call_count += 1
        return 99, {"input": 0, "output": 0, "cache_created": 0, "cache_read": 0}


def test_tracker_cache_hit_skips_llm() -> None:
    """When embedding matches above HIGH threshold, _current_arc_id is set without LLM."""
    idx = ArcEmbeddingIndex(_sample_entries())
    fake_engine = _FakeEngine()
    tracker = ArcStateTracker(fake_engine, arc_index=idx)

    # Feed the exact description the index computed for entry 0 → cosine 1.0.
    from src.t2.core.arc_index import _describe_entry
    desc_0 = _describe_entry(_sample_entries()[0])
    tracker.update_arc_state(desc_0, next_waypoint_id=None, next_arb_idx=None)

    # Cache-hit path is synchronous — no thread to wait on.
    assert tracker.current_arc_id == 0
    assert fake_engine.call_count == 0
    assert tracker.call_counts["cache_hit"] == 1


def test_tracker_ambiguous_fires_llm() -> None:
    """When embedding score is middling (below HIGH), we fire the LLM."""
    # Build an index with one entry and query something wildly different so
    # cosine is below HIGH threshold.
    idx = ArcEmbeddingIndex([{"entry_id": 5, "arc_trajectory": "rising",
                              "world_pressure": "low", "narrative_pacing": "slow",
                              "pending_intent": "exploration"}])
    fake_engine = _FakeEngine()
    tracker = ArcStateTracker(fake_engine, arc_index=idx)

    tracker.update_arc_state("totally unrelated quasi state text",
                             next_waypoint_id=None, next_arb_idx=None)

    # LLM path runs in a background thread; allow it to complete.
    import time
    for _ in range(50):
        if fake_engine.call_count > 0:
            break
        time.sleep(0.02)

    assert fake_engine.call_count == 1
    assert tracker.call_counts["cache_hit"] == 0
    # Either ambiguous or anomaly bucket fired.
    assert tracker.call_counts["ambiguous_fired"] + tracker.call_counts["anomaly_fired"] == 1


def test_tracker_no_index_still_fires() -> None:
    fake_engine = _FakeEngine()
    tracker = ArcStateTracker(fake_engine, arc_index=None)
    tracker.update_arc_state("state", next_waypoint_id=None, next_arb_idx=None)

    import time
    for _ in range(50):
        if fake_engine.call_count > 0:
            break
        time.sleep(0.02)
    assert fake_engine.call_count == 1
    assert tracker.call_counts["disabled_fired"] == 1


def test_tracker_embedding_only_never_fires_llm(monkeypatch) -> None:
    """Step 4c: LOOMBOUND_M2_EMBEDDING_ONLY=1 → LLM is never invoked."""
    monkeypatch.setenv("LOOMBOUND_M2_EMBEDDING_ONLY", "1")
    idx = ArcEmbeddingIndex(_sample_entries())
    fake_engine = _FakeEngine()
    tracker = ArcStateTracker(fake_engine, arc_index=idx)

    # Even a weak match should skip LLM under embedding-only.
    tracker.update_arc_state("anything goes here", next_waypoint_id=None, next_arb_idx=None)
    assert fake_engine.call_count == 0
    assert tracker.call_counts["embedding_only"] == 1
