from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class EventTrace:
    """Standardized observable event emitted from future native flow adapters."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProposedEffect:
    """Bounded overlay effect proposal awaiting deterministic validation."""

    effect_id: str
    target_scope: str
    payload: dict[str, Any] = field(default_factory=dict)


class EffectApplier(Protocol):
    """Deterministic validator/applier for future legal write-back."""

    def validate_and_apply(self, effect: ProposedEffect) -> bool: ...
