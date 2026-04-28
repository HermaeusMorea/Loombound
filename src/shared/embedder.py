"""Lazy local embedder (sentence-transformers) for semantic similarity.

Used by the arc index and effects templater to replace hard string matching
with cosine-based semantic matching. Pure-CPU inference; model is downloaded
on first use (~470 MB). Can be disabled via LOOMBOUND_EMBEDDER_DISABLED=1,
in which case `is_available()` returns False and callers fall back to
string-set intersection.

Design goals:
- Zero cost when not used (no import of sentence-transformers at module load).
- Deterministic unit tests via a fake backend (see `install_fake_backend`).
- No network calls in tests — fake backend returns a hash-based pseudo-embedding.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Callable, Sequence

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_DIM_FAKE = 32  # fake-backend vector dim, only used in tests

_model = None                       # type: ignore[var-annotated]  — real model instance (lazy)
_fake_embed: Callable[[str], list[float]] | None = None


def _disabled() -> bool:
    return os.environ.get("LOOMBOUND_EMBEDDER_DISABLED", "") == "1"


def is_available() -> bool:
    """True if callers should use embedding-based matching."""
    if _disabled():
        return False
    if _fake_embed is not None:
        return True
    # Lazy import: only pay the cost if someone actually needs embeddings.
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def install_fake_backend(fn: Callable[[str], list[float]] | None) -> None:
    """Swap in a deterministic embedding function for tests.

    Pass `None` to uninstall. When installed, `is_available()` returns True
    and `embed()` / `embed_batch()` / `cosine()` all route through `fn`.
    """
    global _fake_embed, _model
    _fake_embed = fn
    _model = None  # force reload if switching back to real backend


def _ensure_model():
    """Load the real sentence-transformers model on first use."""
    global _model
    if _model is not None:
        return _model
    from sentence_transformers import SentenceTransformer
    model_name = os.environ.get("LOOMBOUND_EMBEDDER_MODEL", _DEFAULT_MODEL)
    log.info("Loading embedder model: %s (first-time download may take a minute)", model_name)
    _model = SentenceTransformer(model_name)
    return _model


def embed(text: str) -> list[float]:
    """Embed a single string to a vector."""
    if _fake_embed is not None:
        return _fake_embed(text)
    if _disabled():
        raise RuntimeError("Embedder disabled via LOOMBOUND_EMBEDDER_DISABLED")
    model = _ensure_model()
    vec = model.encode(text, normalize_embeddings=True)
    return list(map(float, vec))


def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    """Embed a list of strings, returning a list of vectors."""
    if _fake_embed is not None:
        return [_fake_embed(t) for t in texts]
    if _disabled():
        raise RuntimeError("Embedder disabled via LOOMBOUND_EMBEDDER_DISABLED")
    model = _ensure_model()
    mat = model.encode(list(texts), normalize_embeddings=True)
    return [list(map(float, row)) for row in mat]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def max_cosine_against(query_vec: Sequence[float], corpus: Sequence[Sequence[float]]) -> float:
    """Return the max cosine between `query_vec` and any vector in `corpus`.

    0.0 when corpus is empty.
    """
    if not corpus:
        return 0.0
    return max(cosine(query_vec, v) for v in corpus)


# ---------------------------------------------------------------------------
# Convenience: hash-based fake backend for tests (no model download needed)
# ---------------------------------------------------------------------------

def hash_based_fake(text: str) -> list[float]:
    """Deterministic 32-float pseudo-embedding derived from a SHA-256 hash.

    Vectors are approximately uniform in [-1, 1]. Not semantically meaningful;
    intended only for exercising the cosine / max_cosine machinery in tests.
    """
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).digest()
    # Take 32 bytes → 32 floats in [-1, 1]
    vec = [(b - 128) / 128.0 for b in digest[:_DIM_FAKE]]
    # Normalize
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]
