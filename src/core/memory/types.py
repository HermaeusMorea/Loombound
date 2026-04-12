"""Memory-layer dataclasses shared by node and run lifecycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeEvent:
    """Structured event captured during one node lifecycle."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NodeChoiceRecord:
    """One arbitration-level choice recorded inside a node."""

    context_id: str
    scene_type: str
    active_rule_id: str | None = None
    active_rule_theme: str | None = None
    player_choice: str | None = None
    destabilized: bool = False
    sanity_delta: int = 0
    local_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ShockRecord:
    """Compact long-lived record of one actual destabilizing choice."""

    context_id: str
    rule_id: str | None
    scene_type: str
    option_id: str
    flags: list[str] = field(default_factory=list)
    sanity_delta: int = 0


@dataclass(slots=True)
class NarratorMood:
    """Structured narrator pressure values for deterministic use later."""

    severity: int = 0
    dread: int = 0
    temptation: int = 0
    leniency: int = 0


@dataclass(slots=True)
class JudgePersonaState:
    """Future-facing narrative bias layer; not yet active in the MVP runtime."""

    tone_bias: str = "neutral"
    summary: str = ""


@dataclass(slots=True)
class NodeMemory:
    """Short-lived memory for one full node lifecycle."""

    node_id: str
    node_type: str
    floor: int
    events: list[NodeEvent] = field(default_factory=list)
    choices_made: list[NodeChoiceRecord] = field(default_factory=list)
    shocks_in_node: list[ShockRecord] = field(default_factory=list)
    sanity_lost_in_node: int = 0
    important_flags: list[str] = field(default_factory=list)
    node_summary: str = ""


@dataclass(slots=True)
class RunMemory:
    """Long-lived run-scoped memory that survives across nodes."""

    sanity: int = 0
    recent_rules: list[str] = field(default_factory=list)
    recent_shocks: list[ShockRecord] = field(default_factory=list)
    theme_counters: dict[str, int] = field(default_factory=dict)
    behavior_counters: dict[str, int] = field(default_factory=dict)
    important_incidents: list[str] = field(default_factory=list)
    narrator_mood: NarratorMood = field(default_factory=NarratorMood)
    persona_summary: str = ""
    persona: JudgePersonaState = field(default_factory=JudgePersonaState)
