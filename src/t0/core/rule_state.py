"""Runtime rule-system state for runs and nodes."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.t0.memory import RuleEvaluation, RuleTemplate


@dataclass(slots=True)
class RuleSystem:
    """Run-scoped rule system state shared across nodes."""

    templates: list[RuleTemplate] = field(default_factory=list)
    recently_used_rule_ids: list[str] = field(default_factory=list)
    rule_use_counts: dict[str, int] = field(default_factory=dict)

    def set_templates(self, templates: list[RuleTemplate]) -> None:
        """Replace the active rule template set for the current run."""

        self.templates = list(templates)

    def record_selected_rule(self, rule_id: str | None) -> None:
        """Track global rule usage after one arbitration finishes."""

        if not rule_id:
            return
        self.recently_used_rule_ids.append(rule_id)
        self.recently_used_rule_ids = self.recently_used_rule_ids[-5:]
        self.rule_use_counts[rule_id] = self.rule_use_counts.get(rule_id, 0) + 1


@dataclass(slots=True)
class NodeRuleState:
    """Node-scoped rule state for one scene lifecycle."""

    available_rule_ids: list[str] = field(default_factory=list)
    candidate_rule_ids: list[str] = field(default_factory=list)
    selected_rule_id: str | None = None
    selection_trace: list[str] = field(default_factory=list)

    def reset_for_arbitration(self) -> None:
        """Clear per-arbitration fields while keeping node-level availability."""

        self.candidate_rule_ids = []
        self.selected_rule_id = None
        self.selection_trace = []

    def record_evaluations(self, evaluations: list[RuleEvaluation]) -> None:
        """Store matched candidate rule ids for this arbitration pass."""

        self.candidate_rule_ids = [item.rule.id for item in evaluations if item.matched]

    def record_selected_rule(self, rule_id: str | None) -> None:
        """Remember the winning rule inside the current node."""

        self.selected_rule_id = rule_id

    def record_selection_trace(self, trace: list[str]) -> None:
        """Store the final selection trace after runtime-adjusted ranking."""

        self.selection_trace = list(trace)
