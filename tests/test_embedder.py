"""Tests for the lazy embedder wrapper."""

import os
import pytest

from src.shared import embedder


def test_disabled_via_env(monkeypatch) -> None:
    monkeypatch.setenv("LOOMBOUND_EMBEDDER_DISABLED", "1")
    # Ensure no fake backend leaks between tests
    embedder.install_fake_backend(None)
    assert embedder.is_available() is False


def test_fake_backend_makes_it_available() -> None:
    embedder.install_fake_backend(embedder.hash_based_fake)
    try:
        assert embedder.is_available() is True
        vec = embedder.embed("hello")
        assert isinstance(vec, list) and len(vec) > 0
    finally:
        embedder.install_fake_backend(None)


def test_hash_based_fake_is_deterministic() -> None:
    a = embedder.hash_based_fake("shelter")
    b = embedder.hash_based_fake("shelter")
    assert a == b


def test_hash_based_fake_different_inputs_differ() -> None:
    a = embedder.hash_based_fake("shelter")
    b = embedder.hash_based_fake("attack")
    assert a != b


def test_cosine_identical_vectors_returns_one() -> None:
    v = [0.5, 0.5, 0.5, 0.5]
    assert embedder.cosine(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_returns_zero() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert embedder.cosine(a, b) == pytest.approx(0.0)


def test_cosine_empty_is_zero() -> None:
    assert embedder.cosine([], [1.0, 2.0]) == 0.0
    assert embedder.cosine([1.0, 2.0], []) == 0.0


def test_max_cosine_against_empty_corpus() -> None:
    assert embedder.max_cosine_against([1.0, 2.0], []) == 0.0


def test_max_cosine_against_picks_the_best() -> None:
    query = [1.0, 0.0, 0.0]
    corpus = [[0.0, 1.0, 0.0], [0.9, 0.1, 0.0], [0.0, 0.0, 1.0]]
    # second vector is closest to query
    assert embedder.max_cosine_against(query, corpus) == pytest.approx(
        embedder.cosine(query, corpus[1])
    )
