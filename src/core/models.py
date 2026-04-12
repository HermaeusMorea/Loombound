from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChoiceOption:
    # One actionable option inside a decision node.
    option_id: str
    label: str
    tags: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChoiceContext:
    # Normalized input for one out-of-combat decision point.
    context_id: str
    decision_type: str
    floor: int
    act: int = 1
    resources: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    options: list[ChoiceOption] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChoiceContext":
        # The CLI and sample data stay JSON-first; convert them once here so
        # the rest of the pipeline can work with typed objects.
        options = [ChoiceOption(**item) for item in payload.get("options", [])]
        return cls(
            context_id=payload["context_id"],
            decision_type=payload["decision_type"],
            floor=payload["floor"],
            act=payload.get("act", 1),
            resources=payload.get("resources", {}),
            tags=payload.get("tags", []),
            options=options,
            metadata=payload.get("metadata", {}),
        )


@dataclass(slots=True)
class RuleMatchSpec:
    # Minimal deterministic trigger conditions for a rule template.
    required_context_tags: list[str] = field(default_factory=list)
    min_hp_ratio: float | None = None
    max_hp_ratio: float | None = None
    min_gold: int | None = None
    max_gold: int | None = None


@dataclass(slots=True)
class RuleTemplate:
    # A reusable rule template: when it applies, what it prefers, and what
    # penalty it threatens if the player breaks ritual.
    id: str
    name: str
    decision_types: list[str]
    theme: str
    priority: int
    match: RuleMatchSpec = field(default_factory=RuleMatchSpec)
    preferred_option_tags: list[str] = field(default_factory=list)
    forbidden_option_tags: list[str] = field(default_factory=list)
    collapse_penalty: int = 0
    narration_keys: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleTemplate":
        # Rules are stored as data so they can be debugged and expanded without
        # burying everything inside hard-coded if/else chains.
        return cls(
            id=payload["id"],
            name=payload["name"],
            decision_types=payload["decision_types"],
            theme=payload["theme"],
            priority=payload["priority"],
            match=RuleMatchSpec(**payload.get("match", {})),
            preferred_option_tags=payload.get("preferred_option_tags", []),
            forbidden_option_tags=payload.get("forbidden_option_tags", []),
            collapse_penalty=payload.get("collapse_penalty", 0),
            narration_keys=payload.get("narration_keys", []),
        )


@dataclass(slots=True)
class RuleEvaluation:
    # Runtime evaluation result for one rule against one current context.
    rule: RuleTemplate
    matched: bool
    reasons: list[str]
    theme_score: float


@dataclass(slots=True)
class OptionResult:
    # Final verdict for one player-facing option after one rule is selected.
    option_id: str
    label: str
    verdict: str
    reasons: list[str]
    collapse_if_taken: int


@dataclass(slots=True)
class NarrationBlock:
    # Optional text wrapper around an already-decided verdict.
    opening: str = ""
    judgement: str = ""
    warning: str = ""


@dataclass(slots=True)
class RunSnapshot:
    # Serializable output of one full judgement pass.
    context_id: str
    selected_rule_id: str | None
    matched_rule_ids: list[str]
    theme_scores: dict[str, float]
    option_results: list[OptionResult]
    ritual_collapse_delta: int
    narration: NarrationBlock = field(default_factory=NarrationBlock)

    def to_dict(self) -> dict[str, Any]:
        # Keep the CLI output explicit and JSON-friendly instead of relying on
        # dataclass internals or repr formatting.
        return {
            "context_id": self.context_id,
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
