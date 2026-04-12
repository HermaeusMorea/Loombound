"""Future overlay integration contracts and read-only adapter interfaces."""

from .contracts import EffectApplier, EventTrace, ProposedEffect
from .read_only_adapter import (
    ObservedOption,
    ObservedScene,
    arbitration_from_observed_scene,
    observed_scene_to_arbitration_payload,
)

__all__ = [
    "EffectApplier",
    "EventTrace",
    "ObservedOption",
    "ObservedScene",
    "ProposedEffect",
    "arbitration_from_observed_scene",
    "observed_scene_to_arbitration_payload",
]
