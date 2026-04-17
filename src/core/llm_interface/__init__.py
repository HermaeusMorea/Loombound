"""LLM content generation pipeline for Loombound.

Two-layer runtime model:
  M2 Classifier (Haiku) → entry_id + per-option effects (per-choice, background)
  Fast Core (gemma3)    → arbitration JSON dicts (full display text)

Public entry point:
  PrefetchCache — manages background gemma3 generation and Haiku arc updates.
"""

from .types import (
    ArbitrationOptionSeed,
    ArbitrationSeed,
    NodeSeedPack,
    ResolvedArbitration,
    PrefetchEntry,
    PrefetchStatus,
)
from .fast_core import FastCoreExpander, FastCoreConfig
from .m2_classifier import M2Classifier, M2ClassifierConfig
from .prefetch import PrefetchCache

__all__ = [
    # Types
    "ArbitrationOptionSeed",
    "ArbitrationSeed",
    "NodeSeedPack",
    "ResolvedArbitration",
    "PrefetchEntry",
    "PrefetchStatus",
    # Fast Core
    "FastCoreExpander",
    "FastCoreConfig",
    # M2 Classifier
    "M2Classifier",
    "M2ClassifierConfig",
    # Prefetch
    "PrefetchCache",
]
