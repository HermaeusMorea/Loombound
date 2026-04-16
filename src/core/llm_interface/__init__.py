"""LLM content generation pipeline for Loombound.

Two-layer asset model:
  Slow Core (Claude)   → NodeSeedPack   (structured plan, tendency language)
  Fast Core (gemma4)   → arbitration JSON dicts (full display text, precise effects)

Public entry point:
  PrefetchCache — manages background generation and cache retrieval.
"""

from .types import (
    ArbitrationOptionSeed,
    ArbitrationSeed,
    NodeSeedPack,
    ResolvedArbitration,
    PrefetchEntry,
    PrefetchStatus,
)
from .collector import build_quasi_description
from .slow_core import SlowCoreClient, SlowCoreConfig, SlowCoreError
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
    # Collector
    "build_quasi_description",
    # Slow Core
    "SlowCoreClient",
    "SlowCoreConfig",
    "SlowCoreError",
    # Fast Core
    "FastCoreExpander",
    "FastCoreConfig",
    # M2 Classifier
    "M2Classifier",
    "M2ClassifierConfig",
    # Prefetch
    "PrefetchCache",
]
