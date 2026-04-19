"""Choose one winning rule from the current candidate set."""

from __future__ import annotations

from src.t0.memory import RuleEvaluation
from src.t0.memory import RunMemory
from src.t0.core.rule_state import RuleSystem

_FRESHNESS_BASE = 0.1
_FRESHNESS_FACTOR = 0.02


def _compute_selection_score(
    evaluation: RuleEvaluation,
    *,
    rule_system: RuleSystem | None = None,
    run_memory: RunMemory | None = None,
) -> tuple[float, int, str]:
    """Rank a candidate rule: freshness penalty applied to a 0-based score."""

    freshness_penalty = 0.0
    if rule_system and evaluation.rule.id in rule_system.recently_used_rule_ids:
        ids = rule_system.recently_used_rule_ids
        last_pos = len(ids) - 1 - ids[::-1].index(evaluation.rule.id)
        recent_distance = last_pos + 1  # 1=oldest in window, N=most recently used
        freshness_penalty = _FRESHNESS_BASE + (_FRESHNESS_FACTOR * recent_distance)

    return (-freshness_penalty, evaluation.rule.priority, evaluation.rule.id)


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
            f"{rule_id}:matched={item.matched}:score={score:.3f}:priority={priority}"
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

    # Pre-compute scores once per candidate so the sort key never re-evaluates.
    # Sort order expresses the current policy:
    # 1. higher adjusted theme fit
    # 2. higher rule priority
    # 3. stable deterministic tie-break by id
    scored = [
        (item, _compute_selection_score(item, rule_system=rule_system, run_memory=run_memory))
        for item in matched
    ]
    return sorted(
        scored,
        key=lambda pair: (-pair[1][0], -pair[1][1], pair[1][2]),
    )[0][0]


# TODO: Revisit tie-breaking once multiple simultaneously active rules are allowed.
