"""Deterministic kernel data models shared across the prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
        """Create an empty context shell for a newly-entered owner."""

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
        """Load one rule template from authored JSON."""

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
class NodeSummary:
    """Compact result promoted from a finished Node back into the Run."""

    node_id: str
    node_type: str
    floor: int
    collapse_delta: int = 0
    important_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


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
        """Convert snapshot output into a stable JSON-friendly structure."""

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
