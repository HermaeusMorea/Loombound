"""Deterministic kernel data models shared across the prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CoreStateView:
    """Structured view of the current deterministic gameplay state."""

    depth: int
    act: int = 1
    health: int | None = None
    max_health: int | None = None
    money: int | None = None
    sanity: int | None = None
    character_id: str | None = None
    scene_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MetaStateView:
    """Overlay-owned state view used by the sanity-pressure system."""

    sanity: int = 0
    active_marks: list[str] = field(default_factory=list)
    narrator_tone: dict[str, int] = field(default_factory=dict)
    theme_bias: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EncounterContext:
    """Judgeable scene input for one encounter."""

    context_id: str
    scene_type: str
    depth: int
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
        depth: int,
        act: int = 1,
        core_state_view: CoreStateView | None = None,
        meta_state_view: MetaStateView | None = None,
    ) -> "EncounterContext":
        """Create an empty context shell for a newly-entered owner."""

        context = cls(
            context_id=context_id,
            scene_type=scene_type,
            depth=depth,
            act=act,
            core_state_view=core_state_view,
            meta_state_view=meta_state_view,
        )
        context.ensure_state_views()
        return context

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EncounterContext":
        """Build an encounter context from flat or nested JSON payloads."""

        if "context" in payload:
            payload = payload["context"]

        scene_type = payload.get("scene_type", payload.get("decision_type"))
        context = cls(
            context_id=payload["context_id"],
            scene_type=scene_type,
            depth=payload["depth"],
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
                depth=self.depth,
                act=self.act,
                health=self.resources.get("health"),
                max_health=self.resources.get("max_health"),
                money=self.resources.get("money"),
                sanity=self.resources.get("sanity"),
                scene_type=self.scene_type,
                metadata={**self.metadata},
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
        """Update the live encounter context in place.

        State views are not refreshed here — callers that need an updated
        core_state_view (e.g. sync_encounter_resources) must assign it
        directly after calling update().
        """

        if resources is not None:
            self.resources = resources
        if tags is not None:
            self.tags = tags
        if metadata is not None:
            self.metadata = metadata
        if scene_type is not None:
            self.scene_type = scene_type


@dataclass(slots=True)
class RuleTemplate:
    """Reusable rule template for deterministic sanity judgement."""

    id: str
    name: str
    decision_types: list[str]
    theme: str
    priority: int
    required_context_tags: list[str] = field(default_factory=list)
    min_health: int | None = None
    max_health: int | None = None
    min_money: int | None = None
    max_money: int | None = None
    min_sanity: int | None = None
    max_sanity: int | None = None
    preferred_option_tags: list[str] = field(default_factory=list)
    forbidden_option_tags: list[str] = field(default_factory=list)
    sanity_penalty: int = 0
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
            min_health=payload.get("min_health", match.get("min_health")),
            max_health=payload.get("max_health", match.get("max_health")),
            min_money=payload.get("min_money", match.get("min_money")),
            max_money=payload.get("max_money", match.get("max_money")),
            min_sanity=payload.get("min_sanity", match.get("min_sanity")),
            max_sanity=payload.get("max_sanity", match.get("max_sanity")),
            preferred_option_tags=payload.get("preferred_option_tags", []),
            forbidden_option_tags=payload.get("forbidden_option_tags", []),
            sanity_penalty=payload.get("sanity_penalty", 0),
            narration_keys=payload.get("narration_keys", []),
        )


@dataclass(slots=True)
class RuleEvaluation:
    """Runtime evaluation result for one rule against one encounter context."""

    rule: RuleTemplate
    matched: bool
    reasons: list[str]


@dataclass(slots=True)
class OptionResult:
    """Final verdict for one player-facing option after a rule is selected."""

    option_id: str
    label: str
    toll: str
    reasons: list[str]
    sanity_cost: int


@dataclass(slots=True)
class NarrationBlock:
    """One-sentence psychological frame shown after a choice."""

    text: str = ""


@dataclass(slots=True)
class EncounterResult:
    """Structured output of one encounter pass before parent state updates."""

    selected_rule_id: str | None
    matched_rule_ids: list[str]
    option_results: list[OptionResult]
    sanity_delta: int
    narration: NarrationBlock = field(default_factory=NarrationBlock)


@dataclass(slots=True)
class WaypointSummary:
    """Compact result promoted from a finished Node back into the Run."""

    waypoint_id: str
    waypoint_type: str
    depth: int
    sanity_delta: int = 0
    important_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunSnapshot:
    """Serializable output of one full encounter pass."""

    encounter_id: str
    selected_rule_id: str | None
    matched_rule_ids: list[str]
    option_results: list[OptionResult]
    sanity_delta: int
    narration: NarrationBlock = field(default_factory=NarrationBlock)

    def to_dict(self) -> dict[str, Any]:
        """Convert snapshot output into a stable JSON-friendly structure."""

        return {
            "encounter_id": self.encounter_id,
            "selected_rule_id": self.selected_rule_id,
            "matched_rule_ids": self.matched_rule_ids,
            "option_results": [
                {
                    "option_id": item.option_id,
                    "label": item.label,
                    "toll": item.toll,
                    "reasons": item.reasons,
                    "sanity_cost": item.sanity_cost,
                }
                for item in self.option_results
            ],
            "sanity_delta": self.sanity_delta,
            "narration": {
                "opening": self.narration.opening,
                "judgement": self.narration.judgement,
                "warning": self.narration.warning,
            },
        }
