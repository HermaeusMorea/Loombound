"""Rule matching, runtime rule state, and stable rule selection."""

from .state import NodeRuleState, RuleSystem

__all__ = ["RuleSystem", "NodeRuleState", "evaluate_rule", "evaluate_rules", "select_rule", "build_selection_trace"]


def evaluate_rule(*args, **kwargs):
    """Lazily import rule matching to avoid package init cycles."""

    from .rule_matcher import evaluate_rule as _evaluate_rule

    return _evaluate_rule(*args, **kwargs)


def evaluate_rules(*args, **kwargs):
    """Lazily import bulk rule evaluation to avoid package init cycles."""

    from .rule_matcher import evaluate_rules as _evaluate_rules

    return _evaluate_rules(*args, **kwargs)


def select_rule(*args, **kwargs):
    """Lazily import rule selection to avoid package init cycles."""

    from .rule_selector import select_rule as _select_rule

    return _select_rule(*args, **kwargs)


def build_selection_trace(*args, **kwargs):
    """Lazily import selection tracing to avoid package init cycles."""

    from .rule_selector import build_selection_trace as _build_selection_trace

    return _build_selection_trace(*args, **kwargs)
