"""Memory-layer dataclasses shared by node and run lifecycles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.t1.memory.scene_history_store import SceneHistoryStore
from src.t2.memory.a2_store import RuntimeTableStore


@dataclass(slots=True)
class NodeEvent:
    """Structured event captured during one node lifecycle."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WaypointChoiceRecord:
    """One encounter-level choice recorded inside a node."""

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
class WaypointMemory:
    """Short-lived memory for one full node lifecycle."""

    waypoint_id: str
    waypoint_type: str
    depth: int
    events: list[NodeEvent] = field(default_factory=list)
    choices_made: list[WaypointChoiceRecord] = field(default_factory=list)
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
    # cache stores
    scene_history: SceneHistoryStore = field(default_factory=SceneHistoryStore)
    tables: RuntimeTableStore = field(default_factory=RuntimeTableStore)
