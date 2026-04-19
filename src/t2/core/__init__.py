"""C2 logic: M2 decision engine (Haiku), prefetch, collector."""

from .types import (
    EncounterOptionSeed, EncounterSeed, WaypointSeedPack,
    ResolvedEncounter, PrefetchEntry, PrefetchStatus,
    EncounterSlot,
)
from .m2_decision_engine import M2DecisionEngine, M2DecisionConfig
from .prefetch import PrefetchCache

__all__ = [
    "EncounterOptionSeed", "EncounterSeed", "WaypointSeedPack",
    "ResolvedEncounter", "PrefetchEntry", "PrefetchStatus",
    "EncounterSlot",
    "M2DecisionEngine", "M2DecisionConfig",
    "PrefetchCache",
]
