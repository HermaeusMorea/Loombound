"""Choose one winning rule from the current candidate set."""

from __future__ import annotations

from src.core.deterministic_kernel import RuleEvaluation
from src.core.memory import RunMemory
from src.core.rule_engine.state import RuleSystem


def _compute_selection_score(
    evaluation: RuleEvaluation,
    *,
    rule_system: RuleSystem | None = None,
    run_memory: RunMemory | None = None,
) -> tuple[float, int, str]:
    """Build a deterministic ranking tuple for one candidate rule.

    The current prototype keeps this intentionally light:
    - base theme fit still dominates
    - repeated recent use applies a small freshness penalty
    - repeated theme exposure in run memory applies a very small bias
    """

    freshness_penalty = 0.0
    if rule_system and evaluation.rule.id in rule_system.recently_used_rule_ids:
        # Penalize repeated recent rules, with a slightly stronger penalty for
        # the most recent entry.
        recent_distance = len(rule_system.recently_used_rule_ids) - rule_system.recently_used_rule_ids.index(evaluation.rule.id)
        freshness_penalty = 0.1 + (0.02 * recent_distance)

    memory_theme_bias = 0.0
    if run_memory:
        memory_theme_bias = min(run_memory.theme_counters.get(evaluation.rule.theme, 0) * 0.05, 0.2)

    adjusted_theme_score = evaluation.theme_score + memory_theme_bias - freshness_penalty
    return (adjusted_theme_score, evaluation.rule.priority, evaluation.rule.id)


def build_selection_trace(
    evaluations: list[RuleEvaluation],
    *,
    rule_system: RuleSystem | None = None,
    run_memory: RunMemory | None = None,
) -> list[str]:
    """Render a compact human-readable trace for rule ranking decisions."""

    trace: list[str] = []
    for item in evaluations:
        score, priority, rule_id = _compute_selection_score(
            item,
            rule_system=rule_system,
            run_memory=run_memory,
        )
        trace.append(
            f"{rule_id}:matched={item.matched}:theme={item.theme_score}:adjusted={score}:priority={priority}"
        )
    return trace


def select_rule(
    evaluations: list[RuleEvaluation],
    *,
    rule_system: RuleSystem | None = None,
    run_memory: RunMemory | None = None,
) -> RuleEvaluation | None:
    """Choose the winning rule with a stable deterministic tie-break."""

    # The prototype allows at most one active rule per decision node.
    matched = [item for item in evaluations if item.matched]
    if not matched:
        return None

    # Sort order expresses the current policy:
    # 1. higher adjusted theme fit
    # 2. higher rule priority
    # 3. stable deterministic tie-break by id
    return sorted(
        matched,
        key=lambda item: (
            -_compute_selection_score(item, rule_system=rule_system, run_memory=run_memory)[0],
            -_compute_selection_score(item, rule_system=rule_system, run_memory=run_memory)[1],
            _compute_selection_score(item, rule_system=rule_system, run_memory=run_memory)[2],
        ),
    )[0]


# TODO: Revisit tie-breaking once multiple simultaneously active rules are allowed.
