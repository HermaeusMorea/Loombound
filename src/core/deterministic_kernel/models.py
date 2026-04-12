from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


OwnerKind = Literal["run", "node"]
ArbitrationStatus = Literal["pending", "evaluated", "applied"]


@dataclass(slots=True)
class CoreStateView:
    """Structured read-only view of native game-owned state."""

    floor: int
    act: int = 1
    hp: int | None = None
    max_hp: int | None = None
    gold: int | None = None
    character_id: str | None = None
    scene_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetaStateView:
    """Overlay-owned state view used by the ritual judge system."""

    ritual_collapse: int = 0
    active_edicts: list[str] = field(default_factory=list)
    judge_mood: dict[str, int] = field(default_factory=dict)
    theme_bias: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArbitrationContext:
    """Judgeable scene input for one arbitration."""

    context_id: str
    scene_type: str
    floor: int
    act: int = 1
    resources: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    core_state_view: CoreStateView | None = None
    meta_state_view: MetaStateView | None = None

    @classmethod
    def empty(
        cls,
        *,
        context_id: str,
        scene_type: str,
        floor: int,
        act: int = 1,
        core_state_view: CoreStateView | None = None,
        meta_state_view: MetaStateView | None = None,
    ) -> "ArbitrationContext":
        """Create an empty context shell for a newly-entered node."""

        context = cls(
            context_id=context_id,
            scene_type=scene_type,
            floor=floor,
            act=act,
            core_state_view=core_state_view,
            meta_state_view=meta_state_view,
        )
        context.ensure_state_views()
        return context

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArbitrationContext":
        """Build an arbitration context from flat or nested JSON payloads."""

        if "context" in payload:
            payload = payload["context"]

        scene_type = payload.get("scene_type", payload.get("decision_type"))
        context = cls(
            context_id=payload["context_id"],
            scene_type=scene_type,
            floor=payload["floor"],
            act=payload.get("act", 1),
            resources=payload.get("resources", {}),
            tags=payload.get("tags", []),
            metadata=payload.get("metadata", {}),
        )
        context.ensure_state_views()
        return context

    def ensure_state_views(self) -> None:
        """Populate minimal state views for the current offline prototype."""

        if self.core_state_view is None:
            self.core_state_view = CoreStateView(
                floor=self.floor,
                act=self.act,
                gold=self.resources.get("gold"),
                scene_type=self.scene_type,
                metadata={
                    "hp_ratio": self.resources.get("hp_ratio"),
                    **self.metadata,
                },
            )
        if self.meta_state_view is None:
            self.meta_state_view = MetaStateView()

    def update(
        self,
        *,
        resources: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        scene_type: str | None = None,
    ) -> None:
        """Update the live arbitration context in place."""

        if resources is not None:
            self.resources = resources
        if tags is not None:
            self.tags = tags
        if metadata is not None:
            self.metadata = metadata
        if scene_type is not None:
            self.scene_type = scene_type
        self.ensure_state_views()


@dataclass(slots=True)
class RuleTemplate:
    """Reusable rule template for deterministic ritual judgement."""

    id: str
    name: str
    decision_types: list[str]
    theme: str
    priority: int
    required_context_tags: list[str] = field(default_factory=list)
    min_hp_ratio: float | None = None
    max_hp_ratio: float | None = None
    min_gold: int | None = None
    max_gold: int | None = None
    preferred_option_tags: list[str] = field(default_factory=list)
    forbidden_option_tags: list[str] = field(default_factory=list)
    collapse_penalty: int = 0
    narration_keys: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleTemplate":
        match = payload.get("match", {})
        return cls(
            id=payload["id"],
            name=payload["name"],
            decision_types=payload["decision_types"],
            theme=payload["theme"],
            priority=payload["priority"],
            required_context_tags=payload.get("required_context_tags", match.get("required_context_tags", [])),
            min_hp_ratio=payload.get("min_hp_ratio", match.get("min_hp_ratio")),
            max_hp_ratio=payload.get("max_hp_ratio", match.get("max_hp_ratio")),
            min_gold=payload.get("min_gold", match.get("min_gold")),
            max_gold=payload.get("max_gold", match.get("max_gold")),
            preferred_option_tags=payload.get("preferred_option_tags", []),
            forbidden_option_tags=payload.get("forbidden_option_tags", []),
            collapse_penalty=payload.get("collapse_penalty", 0),
            narration_keys=payload.get("narration_keys", []),
        )


@dataclass(slots=True)
class RuleEvaluation:
    """Runtime evaluation result for one rule against one arbitration context."""

    rule: RuleTemplate
    matched: bool
    reasons: list[str]
    theme_score: float


@dataclass(slots=True)
class OptionResult:
    """Final verdict for one player-facing option after a rule is selected."""

    option_id: str
    label: str
    verdict: str
    reasons: list[str]
    collapse_if_taken: int


@dataclass(slots=True)
class NarrationBlock:
    """Optional text wrapper around an already-decided verdict."""

    opening: str = ""
    judgement: str = ""
    warning: str = ""


@dataclass(slots=True)
class ArbitrationResult:
    """Structured output of one arbitration pass before parent state updates."""

    selected_rule_id: str | None
    matched_rule_ids: list[str]
    option_results: list[OptionResult]
    ritual_collapse_delta: int
    theme_scores: dict[str, float] = field(default_factory=dict)
    narration: NarrationBlock = field(default_factory=NarrationBlock)


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
    violation_triggered: bool = False
    collapse_delta: int = 0
    local_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ViolationRecord:
    """Compact long-lived record of one actual ritual violation."""

    context_id: str
    rule_id: str | None
    scene_type: str
    option_id: str
    flags: list[str] = field(default_factory=list)
    collapse_delta: int = 0


@dataclass(slots=True)
class JudgeMood:
    """Structured judge attitude values for deterministic use later."""

    severity: int = 0
    suspicion: int = 0
    anti_greed: int = 0
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
    violations_in_node: list[ViolationRecord] = field(default_factory=list)
    collapse_gained_in_node: int = 0
    important_flags: list[str] = field(default_factory=list)
    node_summary: str = ""


@dataclass(slots=True)
class RunMemory:
    """Long-lived run-scoped memory that survives across nodes."""

    ritual_collapse: int = 0
    recent_edicts: list[str] = field(default_factory=list)
    recent_violations: list[ViolationRecord] = field(default_factory=list)
    theme_counters: dict[str, int] = field(default_factory=dict)
    behavior_counters: dict[str, int] = field(default_factory=dict)
    important_incidents: list[str] = field(default_factory=list)
    judge_mood: JudgeMood = field(default_factory=JudgeMood)
    persona_summary: str = ""
    persona: JudgePersonaState = field(default_factory=JudgePersonaState)


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
        """Build an arbitration from JSON shaped around context + options."""

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
        self.result = result
        self.status = "evaluated"

    def mark_applied(self) -> None:
        self.status = "applied"


@dataclass(slots=True)
class NodeSummary:
    """Compact result promoted from a finished Node back into the Run."""

    node_id: str
    node_type: str
    floor: int
    collapse_delta: int = 0
    important_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Node:
    """A run-owned scene container, such as combat, shop, or event."""

    node_id: str
    node_type: str
    floor: int
    parent_run_id: str
    entered_core_state: CoreStateView
    entered_meta_state: MetaStateView
    memory: NodeMemory | None = None
    current_arbitration: Arbitration | None = None
    arbitration_history: list[Arbitration] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = NodeMemory(
                node_id=self.node_id,
                node_type=self.node_type,
                floor=self.floor,
            )

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
        if self.current_arbitration is None:
            return None
        arbitration = self.current_arbitration
        self.arbitration_history.append(arbitration)
        self.current_arbitration = None
        return arbitration

    def build_summary(self, collapse_delta: int = 0, important_flags: list[str] | None = None) -> NodeSummary:
        return NodeSummary(
            node_id=self.node_id,
            node_type=self.node_type,
            floor=self.floor,
            collapse_delta=collapse_delta,
            important_flags=important_flags or [],
        )


@dataclass(slots=True)
class Run:
    """Long-lived container for one full playthrough."""

    run_id: str
    act: int
    floor: int
    core_state: CoreStateView
    meta_state: MetaStateView
    memory: RunMemory | None = None
    current_node: Node | None = None
    current_arbitration: Arbitration | None = None
    node_history: list[NodeSummary] = field(default_factory=list)
    arbitration_history: list[Arbitration] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.memory is None:
            self.memory = RunMemory()
        self.initialize_arbitration()

    def initialize_arbitration(self) -> Arbitration:
        """Create the run-owned arbitration shell when entering the run."""

        arbitration = Arbitration.empty_for_owner(
            arbitration_id=f"run:{self.run_id}",
            owner_kind="run",
            owner_id=self.run_id,
            scene_type="run",
            floor=self.floor,
            act=self.act,
            core_state_view=self.core_state,
            meta_state_view=self.meta_state,
        )
        self.current_arbitration = arbitration
        return arbitration

    def start_node(self, node_id: str, node_type: str, floor: int, memory: NodeMemory | None = None) -> Node:
        node = Node(
            node_id=node_id,
            node_type=node_type,
            floor=floor,
            parent_run_id=self.run_id,
            entered_core_state=self.core_state,
            entered_meta_state=self.meta_state,
            memory=memory,
        )
        node.initialize_arbitration()
        self.current_node = node
        return node

    def close_current_node(self, summary: NodeSummary | None = None) -> Node | None:
        if self.current_node is None:
            return None
        node = self.current_node
        if summary is not None:
            self.node_history.append(summary)
        self.current_node = None
        return node

    def begin_run_arbitration(self, arbitration: Arbitration) -> None:
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
        if self.current_arbitration is None:
            return None
        arbitration = self.current_arbitration
        self.arbitration_history.append(arbitration)
        self.current_arbitration = None
        return arbitration


@dataclass(slots=True)
class RunSnapshot:
    """Serializable output of one full arbitration pass."""

    arbitration_id: str
    selected_rule_id: str | None
    matched_rule_ids: list[str]
    theme_scores: dict[str, float]
    option_results: list[OptionResult]
    ritual_collapse_delta: int
    narration: NarrationBlock = field(default_factory=NarrationBlock)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arbitration_id": self.arbitration_id,
            "selected_rule_id": self.selected_rule_id,
            "matched_rule_ids": self.matched_rule_ids,
            "theme_scores": self.theme_scores,
            "option_results": [
                {
                    "option_id": item.option_id,
                    "label": item.label,
                    "verdict": item.verdict,
                    "reasons": item.reasons,
                    "collapse_if_taken": item.collapse_if_taken,
                }
                for item in self.option_results
            ],
            "ritual_collapse_delta": self.ritual_collapse_delta,
            "narration": {
                "opening": self.narration.opening,
                "judgement": self.narration.judgement,
                "warning": self.narration.warning,
            },
        }
