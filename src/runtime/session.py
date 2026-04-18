"""Runtime-owned lifecycle objects for runs, nodes, and encounters."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from src.t0.memory.models import (
    EncounterContext,
    EncounterResult,
    CoreStateView,
    MetaStateView,
    WaypointSummary,
)
from src.t0.memory.types import WaypointMemory, RunMemory
from src.t0.core.rule_state import WaypointRuleState, RuleSystem


OwnerKind = Literal["run", "node"]
EncounterStatus = Literal["pending", "evaluated", "applied"]


@dataclass(slots=True)
class Encounter:
    """A judgeable unit owned by either a Run or a Waypoint."""

    encounter_id: str
    owner_kind: OwnerKind
    owner_id: str
    context: EncounterContext
    options: list[dict[str, Any]] = field(default_factory=list)
    selected_option_id: str | None = None
    status: EncounterStatus = "pending"
    result: EncounterResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty_for_owner(
        cls,
        *,
        encounter_id: str,
        owner_kind: OwnerKind,
        owner_id: str,
        scene_type: str,
        depth: int,
        act: int = 1,
        core_state_view: CoreStateView | None = None,
        meta_state_view: MetaStateView | None = None,
    ) -> "Encounter":
        """Create an empty encounter shell owned by a Run or Waypoint."""

        return cls(
            encounter_id=encounter_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            context=EncounterContext.empty(
                context_id=encounter_id,
                scene_type=scene_type,
                depth=depth,
                act=act,
                core_state_view=core_state_view,
                meta_state_view=meta_state_view,
            ),
        )

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        owner_kind: OwnerKind,
        owner_id: str,
    ) -> "Encounter":
        """Build an encounter from JSON shaped around context plus options."""

        context = EncounterContext.from_dict(payload)
        return cls(
            encounter_id=payload.get("encounter_id", context.context_id),
            owner_kind=owner_kind,
            owner_id=owner_id,
            context=context,
            options=[dict(item) for item in payload.get("options", [])],
            metadata=payload.get("metadata", {}),
        )

    def update_context(self, **changes: Any) -> None:
        """Update the attached encounter context in place."""

        self.context.update(**changes)

    def load_from_dict(self, payload: dict[str, Any]) -> None:
        """Populate or refresh this encounter from a structured payload."""

        context = EncounterContext.from_dict(payload)
        self.encounter_id = payload.get("encounter_id", context.context_id)
        self.context = context
        self.options = [dict(item) for item in payload.get("options", [])]
        self.metadata = payload.get("metadata", {})
        self.selected_option_id = None
        self.result = None
        self.status = "pending"

    def replace_options(self, options: list[dict[str, Any]]) -> None:
        """Replace the full option set for this encounter."""

        self.options = [dict(item) for item in options]
        if self.selected_option_id and self.get_option(self.selected_option_id) is None:
            self.selected_option_id = None

    def upsert_option(self, option: dict[str, Any]) -> None:
        """Insert or replace one option by option_id."""

        option_id = option["option_id"]
        for index, current in enumerate(self.options):
            if current["option_id"] == option_id:
                self.options[index] = dict(option)
                return
        self.options.append(dict(option))

    def remove_option(self, option_id: str) -> None:
        """Remove one option if it exists."""

        self.options = [item for item in self.options if item["option_id"] != option_id]
        if self.selected_option_id == option_id:
            self.selected_option_id = None

    def select_option(self, option_id: str) -> None:
        """Record the currently chosen option for this encounter."""

        if self.get_option(option_id) is None:
            raise ValueError(f"Unknown option_id '{option_id}' for encounter '{self.encounter_id}'.")
        self.selected_option_id = option_id

    def get_option(self, option_id: str) -> dict[str, Any] | None:
        """Return the matching option payload, if present."""

        for item in self.options:
            if item["option_id"] == option_id:
                return item
        return None

    def set_result(self, result: EncounterResult) -> None:
        """Attach the evaluated result produced by the deterministic pipeline."""

        self.result = result
        self.status = "evaluated"

    def mark_applied(self) -> None:
        """Mark the encounter as fully consumed by its owner."""

        self.status = "applied"


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
        """Create the node-owned encounter shell when entering the node."""

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
        """Attach an externally created encounter to this node."""

        self.current_encounter = encounter

    def load_current_encounter(self, payload: dict[str, Any]) -> Encounter:
        """Load scene data into the node-owned encounter shell."""

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
        """Build a compact node summary from accumulated node-local state."""

        memory = self.memory
        encounter_count = len(self.encounter_history)
        event_count = len(memory.events) if memory else 0
        chosen_option_ids = [item.player_choice for item in memory.choices_made if item.player_choice] if memory else []
        selected_rule_ids = [item.active_rule_id for item in memory.choices_made if item.active_rule_id] if memory else []
        shock_count = len(memory.shocks_in_node) if memory else 0
        summary_flags = important_flags or (memory.important_flags.copy() if memory else [])
        summary_sanity = sanity_delta or (memory.sanity_lost_in_node if memory else 0)
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
        """Create and activate a node under this run."""

        node = Waypoint(
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
        node.initialize_encounter()
        self.current_waypoint = node
        return node

    def close_current_waypoint(self, summary: WaypointSummary | None = None) -> Waypoint | None:
        """Archive the current node and optionally store a compact summary."""

        if self.current_waypoint is None:
            return None
        node = self.current_waypoint
        if summary is not None:
            self.waypoint_history.append(summary)
        self.current_waypoint = None
        return node

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
