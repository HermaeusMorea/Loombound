"""Collector — translate Loombound runtime state into quasi descriptions.

Produces a structured text payload for Slow Core (Claude) describing:
  - Current gameplay state (health / money / sanity as tendency bands)
  - Run history (recent shocks, theme patterns, narrator mood)
  - Node trajectory (which nodes were visited and what happened)

This is the upward direction: precise state → quasi language.
Slow Core never sees exact numbers — only bands and narrative signals.
"""

from __future__ import annotations

from src.core.deterministic_kernel.models import CoreStateView, NodeSummary
from src.core.memory.m1_store import M1Entry
from src.core.memory.types import NodeMemory, RunMemory


# ---------------------------------------------------------------------------
# Tendency band helpers
# ---------------------------------------------------------------------------

def _band(value: int | None, lo: int, hi: int) -> str:
    """Discretize a precise value into a five-level tendency band."""
    if value is None:
        return "unknown"
    if hi <= lo:
        return "moderate"
    ratio = (value - lo) / (hi - lo)
    if ratio <= 0.2:
        return "very_low"
    elif ratio <= 0.4:
        return "low"
    elif ratio <= 0.6:
        return "moderate"
    elif ratio <= 0.8:
        return "high"
    else:
        return "very_high"


def _direction(value: int | None, previous: int | None) -> str:
    if value is None or previous is None:
        return "stable"
    if value > previous:
        return "rising"
    if value < previous:
        return "falling"
    return "stable"


# ---------------------------------------------------------------------------
# M1 entry builder (deterministic — no LLM)
# ---------------------------------------------------------------------------

def build_m1_entry(
    core_state: CoreStateView,
    run_memory: RunMemory,
    node_memory: NodeMemory,
) -> M1Entry:
    """Translate completed node M0 data into a quasi-precise M1Entry.

    All logic is deterministic; no LLM is involved.
    Called from play_cli immediately after update_after_node().
    """
    # pressure_level: derive from current sanity band
    pressure_level = _band(core_state.sanity, 0, core_state.max_health or 10)
    # Map five-level band to four-level IRIS pressure scale
    pressure_map = {
        "very_low": "critical",
        "low": "high",
        "moderate": "moderate",
        "high": "low",
        "very_high": "low",
    }
    pressure_level = pressure_map.get(pressure_level, "moderate")

    # resource_trajectory: sanity lost this node + cumulative mood
    sanity_lost = node_memory.sanity_lost_in_node
    severity = run_memory.narrator_mood.severity
    if sanity_lost >= 3 or severity >= 4:
        resource_trajectory = "critical"
    elif sanity_lost >= 2 or severity >= 2:
        resource_trajectory = "depleting"
    elif sanity_lost == 0 and run_memory.narrator_mood.leniency >= 2:
        resource_trajectory = "recovering"
    else:
        resource_trajectory = "stable"

    # outcome_class
    if node_memory.shocks_in_node:
        outcome_class = "turbulent"
    elif node_memory.important_flags:
        outcome_class = "deepened"
    else:
        outcome_class = "stable"

    # narrative_thread: highest-frequency theme this run
    theme_counters = run_memory.theme_counters
    if theme_counters:
        narrative_thread = max(theme_counters, key=theme_counters.__getitem__)
    else:
        narrative_thread = ""

    return M1Entry(
        node_id=node_memory.node_id,
        scene_type=node_memory.node_type,
        pressure_level=pressure_level,
        resource_trajectory=resource_trajectory,
        outcome_class=outcome_class,
        narrative_thread=narrative_thread,
        floor=node_memory.floor,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _build_state_sections(
    core_state: CoreStateView,
    run_memory: RunMemory,
    node_history: list[NodeSummary],
    previous_core_state: CoreStateView | None = None,
) -> list[str]:
    """Build the shared state sections used by both classifier and planner."""
    sections: list[str] = []

    h_band = _band(core_state.health, 0, core_state.max_health or 10)
    m_band = _band(core_state.money, 0, 15)
    s_band = _band(core_state.sanity, 0, 10)

    prev = previous_core_state
    h_dir = _direction(core_state.health, prev.health if prev else None)
    m_dir = _direction(core_state.money, prev.money if prev else None)
    s_dir = _direction(core_state.sanity, prev.sanity if prev else None)

    sections.append("## Current state (quasi)")
    sections.append(f"  health:  {h_band} ({h_dir})")
    sections.append(f"  money:   {m_band} ({m_dir})")
    sections.append(f"  sanity:  {s_band} ({s_dir})")
    sections.append(f"  floor:   {core_state.floor},  act: {core_state.act}")

    mood = run_memory.narrator_mood
    mood_parts = []
    if mood.severity:
        mood_parts.append(f"severity {mood.severity}")
    if mood.dread:
        mood_parts.append(f"dread {mood.dread}")
    if mood.temptation:
        mood_parts.append(f"temptation {mood.temptation}")
    if mood_parts:
        sections.append(f"  narrator mood: {', '.join(mood_parts)}")

    if run_memory.theme_counters:
        top_themes = sorted(
            run_memory.theme_counters.items(), key=lambda kv: kv[1], reverse=True
        )[:3]
        theme_str = ", ".join(f"{t}×{n}" for t, n in top_themes)
        sections.append(f"  dominant themes: {theme_str}")

    if run_memory.important_incidents:
        recent = run_memory.important_incidents[-3:]
        sections.append("\n## Recent incidents")
        for inc in recent:
            sections.append(f"  - {inc}")

    if run_memory.recent_shocks:
        sections.append("\n## Recent destabilizing choices")
        for shock in run_memory.recent_shocks[-3:]:
            sections.append(
                f"  - [{shock.scene_type}] option={shock.option_id}"
                f"  sanity={shock.sanity_delta}"
            )

    if node_history:
        sections.append(f"\n## Node trajectory ({len(node_history)} completed)")
        for summary in node_history[-4:]:
            flags = ", ".join(summary.important_flags) if summary.important_flags else "none"
            sections.append(
                f"  [{summary.node_type}] floor={summary.floor}"
                f"  sanity_delta={summary.sanity_delta}  flags={flags}"
            )
    else:
        sections.append("\n## Node trajectory\n  Run just started — no nodes completed yet.")

    if run_memory.m1.entries:
        sections.append("\n## Scene history (M1 — last 3 nodes)")
        for line in run_memory.m1.to_prompt_lines(n=3):
            sections.append(line)

    return sections


def build_classifier_input(
    core_state: CoreStateView,
    run_memory: RunMemory,
    node_history: list[NodeSummary],
    previous_core_state: CoreStateView | None = None,
) -> str:
    """Build the input sent to the M2 arc-state classifier (Claude).

    Contains only mechanical game state — no planning request.
    The classifier's job is purely structural: pick the best-matching Table A row.
    """
    sections = _build_state_sections(
        core_state, run_memory, node_history, previous_core_state
    )
    sections.append("\nClassify the arc state that best matches the current game state above.")
    return "\n".join(sections)


def build_quasi_description(
    core_state: CoreStateView,
    run_memory: RunMemory,
    node_history: list[NodeSummary],
    *,
    target_node_id: str,
    arbitration_count: int,
    previous_core_state: CoreStateView | None = None,
) -> str:
    """Build the user-message payload sent to Slow Core (dynamic path).

    Args:
        core_state:           Current precise state after the last node.
        run_memory:           Long-lived run memory (shocks, themes, mood).
        node_history:         Ordered list of NodeSummary from completed nodes.
        target_node_id:       The node ID Slow Core should plan content for.
        arbitration_count:    How many arbitrations to generate for that node.
        previous_core_state:  State before the last node — used for direction signals.
    """
    sections = _build_state_sections(
        core_state, run_memory, node_history, previous_core_state
    )

    sections.append(
        f"\n## Your task\n"
        f"Plan content for node '{target_node_id}'.\n"
        f"Generate exactly {arbitration_count} arbitration(s).\n"
        f"Each arbitration must fit the current state and narrative trajectory above.\n"
        f"Use tendency language only — no exact numbers in scene_concept or sanity_axis.\n"
        f"Call plan_node_content with your plan."
    )

    return "\n".join(sections)
