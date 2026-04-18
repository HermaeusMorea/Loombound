"""Runtime-owned lifecycle objects for runs, nodes, and arbitrations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from src.t0.memory.models import (
    ArbitrationContext,
    ArbitrationResult,
    CoreStateView,
    MetaStateView,
    NodeSummary,
)
from src.t0.memory.types import NodeMemory, RunMemory
from src.t0.core.rule_state import NodeRuleState, RuleSystem


OwnerKind = Literal["run", "node"]
ArbitrationStatus = Literal["pending", "evaluated", "applied"]


@dataclass(slots=True)
class Arbitration:
    """A judgeable unit owned by either a Run or a Node."""

    arbitration_id: str
    owner_kind: OwnerKind
    owner_id: str
    context: ArbitrationContext
    options: list[dict[str, Any]] = field(default_factory=list)
    selected_option_id: str | None = None
    status: ArbitrationStatus = "pending"
    result: ArbitrationResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty_for_owner(
        cls,
        *,
        arbitration_id: str,
        owner_kind: OwnerKind,
        owner_id: str,
        scene_type: str,
        floor: int,
        act: int = 1,
        core_state_view: CoreStateView | None = None,
        meta_state_view: MetaStateView | None = None,
    ) -> "Arbitration":
        """Create an empty arbitration shell owned by a Run or Node."""

        return cls(
            arbitration_id=arbitration_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            context=ArbitrationContext.empty(
                context_id=arbitration_id,
                scene_type=scene_type,
                floor=floor,
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
    ) -> "Arbitration":
        """Build an arbitration from JSON shaped around context plus options."""

        context = ArbitrationContext.from_dict(payload)
        return cls(
            arbitration_id=payload.get("arbitration_id", context.context_id),
            owner_kind=owner_kind,
            owner_id=owner_id,
            context=context,
            options=[dict(item) for item in payload.get("options", [])],
            metadata=payload.get("metadata", {}),
        )

    def update_context(self, **changes: Any) -> None:
        """Update the attached arbitration context in place."""

        self.context.update(**changes)

    def load_from_dict(self, payload: dict[str, Any]) -> None:
        """Populate or refresh this arbitration from a structured payload."""

        context = ArbitrationContext.from_dict(payload)
        self.arbitration_id = payload.get("arbitration_id", context.context_id)
        self.context = context
        self.options = [dict(item) for item in payload.get("options", [])]
        self.metadata = payload.get("metadata", {})
        self.selected_option_id = None
        self.result = None
        self.status = "pending"

    def replace_options(self, options: list[dict[str, Any]]) -> None:
        """Replace the full option set for this arbitration."""

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
        """Record the currently chosen option for this arbitration."""

        if self.get_option(option_id) is None:
            raise ValueError(f"Unknown option_id '{option_id}' for arbitration '{self.arbitration_id}'.")
        self.selected_option_id = option_id

    def get_option(self, option_id: str) -> dict[str, Any] | None:
        """Return the matching option payload, if present."""

        for item in self.options:
            if item["option_id"] == option_id:
                return item
        return None

    def set_result(self, result: ArbitrationResult) -> None:
        """Attach the evaluated result produced by the deterministic pipeline."""

        self.result = result
        self.status = "evaluated"

    def mark_applied(self) -> None:
        """Mark the arbitration as fully consumed by its owner."""

        self.status = "applied"


@dataclass(slots=True)
class Node:
    """A run-owned scene container, such as a crossroads, archive, or market."""

    node_id: str
    node_type: str
    floor: int
    parent_run_id: str
    entered_core_state: CoreStateView
    entered_meta_state: MetaStateView
    memory: NodeMemory | None = None
    rule_state: NodeRuleState | None = None
    current_arbitration: Arbitration | None = None
    arbitration_history: list[Arbitration] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = NodeMemory(
                node_id=self.node_id,
                node_type=self.node_type,
                floor=self.floor,
            )
        if self.rule_state is None:
            self.rule_state = NodeRuleState()

    def initialize_arbitration(self) -> Arbitration:
        """Create the node-owned arbitration shell when entering the node."""

        arbitration = Arbitration.empty_for_owner(
            arbitration_id=f"{self.node_type}:{self.node_id}",
            owner_kind="node",
            owner_id=self.node_id,
            scene_type=self.node_type,
            floor=self.floor,
            act=self.entered_core_state.act,
            core_state_view=self.entered_core_state,
            meta_state_view=self.entered_meta_state,
        )
        self.current_arbitration = arbitration
        return arbitration

    def begin_arbitration(self, arbitration: Arbitration) -> None:
        """Attach an externally created arbitration to this node."""

        self.current_arbitration = arbitration

    def load_current_arbitration(self, payload: dict[str, Any]) -> Arbitration:
        """Load scene data into the node-owned arbitration shell."""

        if self.current_arbitration is None:
            self.initialize_arbitration()
        self.current_arbitration.load_from_dict(payload)
        self.current_arbitration.owner_kind = "node"
        self.current_arbitration.owner_id = self.node_id
        return self.current_arbitration

    def close_current_arbitration(self) -> Arbitration | None:
        """Archive the current arbitration and clear the live slot."""

        if self.current_arbitration is None:
            return None
        arbitration = self.current_arbitration
        self.arbitration_history.append(arbitration)
        self.current_arbitration = None
        return arbitration

    def build_summary(self, sanity_delta: int = 0, important_flags: list[str] | None = None) -> NodeSummary:
        """Build a compact node summary from accumulated node-local state."""

        memory = self.memory
        arbitration_count = len(self.arbitration_history)
        event_count = len(memory.events) if memory else 0
        chosen_option_ids = [item.player_choice for item in memory.choices_made if item.player_choice] if memory else []
        selected_rule_ids = [item.active_rule_id for item in memory.choices_made if item.active_rule_id] if memory else []
        shock_count = len(memory.shocks_in_node) if memory else 0
        summary_flags = important_flags or (memory.important_flags.copy() if memory else [])
        summary_sanity = sanity_delta or (memory.sanity_lost_in_node if memory else 0)
        return NodeSummary(
            node_id=self.node_id,
            node_type=self.node_type,
            floor=self.floor,
            sanity_delta=summary_sanity,
            important_flags=summary_flags,
            metadata={
                "arbitration_count": arbitration_count,
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
    current_node: Node | None = None
    current_arbitration: Arbitration | None = None
    node_history: list[NodeSummary] = field(default_factory=list)
    arbitration_history: list[Arbitration] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = RunMemory()
        if self.rule_system is None:
            self.rule_system = RuleSystem()
        self.initialize_arbitration()

    def initialize_arbitration(self) -> Arbitration:
        """Create the run-owned arbitration shell when entering the run."""

        arbitration = Arbitration.empty_for_owner(
            arbitration_id=f"run:{self.run_id}",
            owner_kind="run",
            owner_id=self.run_id,
            scene_type="run",
            floor=self.core_state.floor,
            act=self.core_state.act,
            core_state_view=replace(self.core_state),
            meta_state_view=replace(self.meta_state),
        )
        self.current_arbitration = arbitration
        return arbitration

    def start_node(self, node_id: str, node_type: str, floor: int, memory: NodeMemory | None = None) -> Node:
        """Create and activate a node under this run."""

        node = Node(
            node_id=node_id,
            node_type=node_type,
            floor=floor,
            parent_run_id=self.run_id,
            entered_core_state=replace(self.core_state),
            entered_meta_state=replace(self.meta_state),
            memory=memory,
            rule_state=NodeRuleState(
                available_rule_ids=[template.id for template in self.rule_system.templates] if self.rule_system else []
            ),
        )
        node.initialize_arbitration()
        self.current_node = node
        return node

    def close_current_node(self, summary: NodeSummary | None = None) -> Node | None:
        """Archive the current node and optionally store a compact summary."""

        if self.current_node is None:
            return None
        node = self.current_node
        if summary is not None:
            self.node_history.append(summary)
        self.current_node = None
        return node

    def begin_run_arbitration(self, arbitration: Arbitration) -> None:
        """Replace the current run-owned arbitration object."""

        self.current_arbitration = arbitration

    def load_current_arbitration(self, payload: dict[str, Any]) -> Arbitration:
        """Load run-level scene data into the run-owned arbitration shell."""

        if self.current_arbitration is None:
            self.initialize_arbitration()
        self.current_arbitration.load_from_dict(payload)
        self.current_arbitration.owner_kind = "run"
        self.current_arbitration.owner_id = self.run_id
        return self.current_arbitration

    def close_current_arbitration(self) -> Arbitration | None:
        """Archive the current run-owned arbitration and clear the live slot."""

        if self.current_arbitration is None:
            return None
        arbitration = self.current_arbitration
        self.arbitration_history.append(arbitration)
        self.current_arbitration = None
        return arbitration
