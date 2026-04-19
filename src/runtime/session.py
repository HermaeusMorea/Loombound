"""Runtime-owned lifecycle objects for runs, nodes, and encounters."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from src.t0.memory.encounter import Encounter
from src.t0.memory.models import (
    CoreStateView,
    MetaStateView,
    WaypointSummary,
)
from src.t0.memory.types import WaypointMemory, RunMemory
from src.t0.core.rule_state import WaypointRuleState, RuleSystem


@dataclass(slots=True)
class Waypoint:
    """A run-owned scene container, such as a crossroads, archive, or market."""

    waypoint_id: str
    waypoint_type: str
    depth: int
    parent_run_id: str
    entered_core_state: CoreStateView
    entered_meta_state: MetaStateView
    memory: WaypointMemory | None = None
    rule_state: WaypointRuleState | None = None
    current_encounter: Encounter | None = None
    encounter_history: list[Encounter] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = WaypointMemory(
                waypoint_id=self.waypoint_id,
                waypoint_type=self.waypoint_type,
                depth=self.depth,
            )
        if self.rule_state is None:
            self.rule_state = WaypointRuleState()

    def initialize_encounter(self) -> Encounter:
        """Create the waypoint-owned encounter shell when entering the waypoint."""

        encounter = Encounter.empty_for_owner(
            encounter_id=f"{self.waypoint_type}:{self.waypoint_id}",
            owner_kind="node",
            owner_id=self.waypoint_id,
            scene_type=self.waypoint_type,
            depth=self.depth,
            act=self.entered_core_state.act,
            core_state_view=self.entered_core_state,
            meta_state_view=self.entered_meta_state,
        )
        self.current_encounter = encounter
        return encounter

    def begin_encounter(self, encounter: Encounter) -> None:
        """Attach an externally created encounter to this waypoint."""

        self.current_encounter = encounter

    def load_current_encounter(self, payload: dict[str, Any]) -> Encounter:
        """Load scene data into the waypoint-owned encounter shell."""

        if self.current_encounter is None:
            self.initialize_encounter()
        self.current_encounter.load_from_dict(payload)
        self.current_encounter.owner_kind = "node"
        self.current_encounter.owner_id = self.waypoint_id
        return self.current_encounter

    def close_current_encounter(self) -> Encounter | None:
        """Archive the current encounter and clear the live slot."""

        if self.current_encounter is None:
            return None
        encounter = self.current_encounter
        self.encounter_history.append(encounter)
        self.current_encounter = None
        return encounter

    def build_summary(self, sanity_delta: int = 0, important_flags: list[str] | None = None) -> WaypointSummary:
        """Build a compact waypoint summary from accumulated waypoint-local state."""

        memory = self.memory
        encounter_count = len(self.encounter_history)
        event_count = len(memory.events) if memory else 0
        chosen_option_ids = [item.player_choice for item in memory.choices_made if item.player_choice] if memory else []
        selected_rule_ids = [item.active_rule_id for item in memory.choices_made if item.active_rule_id] if memory else []
        shock_count = len(memory.shocks_in_waypoint) if memory else 0
        summary_flags = important_flags or (memory.important_flags.copy() if memory else [])
        summary_sanity = sanity_delta or (memory.sanity_lost_in_waypoint if memory else 0)
        return WaypointSummary(
            waypoint_id=self.waypoint_id,
            waypoint_type=self.waypoint_type,
            depth=self.depth,
            sanity_delta=summary_sanity,
            important_flags=summary_flags,
            metadata={
                "encounter_count": encounter_count,
                "event_count": event_count,
                "selected_rule_ids": selected_rule_ids,
                "chosen_option_ids": chosen_option_ids,
                "shock_count": shock_count,
            },
        )


@dataclass(slots=True)
class Run:
    """Long-lived container for one full playthrough."""

    run_id: str
    core_state: CoreStateView
    meta_state: MetaStateView
    memory: RunMemory | None = None
    rule_system: RuleSystem | None = None
    current_waypoint: Waypoint | None = None
    current_encounter: Encounter | None = None
    waypoint_history: list[WaypointSummary] = field(default_factory=list)
    encounter_history: list[Encounter] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = RunMemory()
        if self.rule_system is None:
            self.rule_system = RuleSystem()
        self.initialize_encounter()

    def initialize_encounter(self) -> Encounter:
        """Create the run-owned encounter shell when entering the run."""

        encounter = Encounter.empty_for_owner(
            encounter_id=f"run:{self.run_id}",
            owner_kind="run",
            owner_id=self.run_id,
            scene_type="run",
            depth=self.core_state.depth,
            act=self.core_state.act,
            core_state_view=replace(self.core_state),
            meta_state_view=replace(self.meta_state),
        )
        self.current_encounter = encounter
        return encounter

    def start_waypoint(self, waypoint_id: str, waypoint_type: str, depth: int, memory: WaypointMemory | None = None) -> Waypoint:
        """Create and activate a waypoint under this run."""

        waypoint = Waypoint(
            waypoint_id=waypoint_id,
            waypoint_type=waypoint_type,
            depth=depth,
            parent_run_id=self.run_id,
            entered_core_state=replace(self.core_state),
            entered_meta_state=replace(self.meta_state),
            memory=memory,
            rule_state=WaypointRuleState(
                available_rule_ids=[template.id for template in self.rule_system.templates] if self.rule_system else []
            ),
        )
        waypoint.initialize_encounter()
        self.current_waypoint = waypoint
        return waypoint

    def close_current_waypoint(self, summary: WaypointSummary | None = None) -> Waypoint | None:
        """Archive the current waypoint and optionally store a compact summary."""

        if self.current_waypoint is None:
            return None
        waypoint = self.current_waypoint
        if summary is not None:
            self.waypoint_history.append(summary)
        self.current_waypoint = None
        return waypoint

    def begin_run_encounter(self, encounter: Encounter) -> None:
        """Replace the current run-owned encounter object."""

        self.current_encounter = encounter

    def load_current_encounter(self, payload: dict[str, Any]) -> Encounter:
        """Load run-level scene data into the run-owned encounter shell."""

        if self.current_encounter is None:
            self.initialize_encounter()
        self.current_encounter.load_from_dict(payload)
        self.current_encounter.owner_kind = "run"
        self.current_encounter.owner_id = self.run_id
        return self.current_encounter

    def close_current_encounter(self) -> Encounter | None:
        """Archive the current run-owned encounter and clear the live slot."""

        if self.current_encounter is None:
            return None
        encounter = self.current_encounter
        self.encounter_history.append(encounter)
        self.current_encounter = None
        return encounter
