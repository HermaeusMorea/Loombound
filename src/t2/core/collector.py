"""Collector — translate Loombound runtime state into quasi descriptions.

Produces a structured text payload for Slow Core (Claude) describing:
  - Current gameplay state (health / money / sanity as tendency bands)
  - Run history (recent shocks, theme patterns, narrator mood)
  - Node trajectory (which nodes were visited and what happened)

This is the upward direction: precise state → quasi language.
Slow Core never sees exact numbers — only bands and narrative signals.
"""

from __future__ import annotations

from src.shared import config
from src.t0.memory.models import CoreStateView, WaypointSummary
from src.t1.memory.a1_store import A1Entry
from src.t0.memory.types import WaypointMemory, RunMemory


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
    t1, t2, t3, t4 = config.BAND_THRESHOLDS
    if ratio <= t1:
        return "very_low"
    elif ratio <= t2:
        return "low"
    elif ratio <= t3:
        return "moderate"
    elif ratio <= t4:
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

def build_a1_entry(
    core_state: CoreStateView,
    run_memory: RunMemory,
    waypoint_memory: WaypointMemory,
) -> A1Entry:
    """Translate completed waypoint A0 data into a tendency-level A1Entry.

    All logic is deterministic; no LLM is involved.
    Called from play_cli immediately after update_after_node().
    """
    # pressure_level: derive from current sanity band
    pressure_level = _band(core_state.sanity, 0, 100)
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
    sanity_lost = waypoint_memory.sanity_lost_in_node
    severity = run_memory.narrator_mood.severity
    if sanity_lost >= config.SANITY_CRITICAL_THRESHOLD or severity >= config.MOOD_SEVERITY_HIGH:
        resource_trajectory = "critical"
    elif sanity_lost >= config.SANITY_DEPLETING_THRESHOLD or severity >= config.MOOD_LENIENCY_LOW:
        resource_trajectory = "depleting"
    elif sanity_lost == 0 and run_memory.narrator_mood.leniency >= config.MOOD_LENIENCY_LOW:
        resource_trajectory = "recovering"
    else:
        resource_trajectory = "stable"

    # outcome_class
    if waypoint_memory.shocks_in_node:
        outcome_class = "turbulent"
    elif waypoint_memory.important_flags:
        outcome_class = "deepened"
    else:
        outcome_class = "stable"

    # narrative_thread: highest-frequency theme this run
    theme_counters = run_memory.theme_counters
    if theme_counters:
        narrative_thread = max(theme_counters, key=theme_counters.__getitem__)
    else:
        narrative_thread = ""

    return A1Entry(
        waypoint_id=waypoint_memory.waypoint_id,
        scene_type=waypoint_memory.waypoint_type,
        pressure_level=pressure_level,
        resource_trajectory=resource_trajectory,
        outcome_class=outcome_class,
        narrative_thread=narrative_thread,
        depth=waypoint_memory.depth,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _build_state_sections(
    core_state: CoreStateView,
    run_memory: RunMemory,
    waypoint_history: list[WaypointSummary],
    previous_core_state: CoreStateView | None = None,
    current_waypoint_memory: WaypointMemory | None = None,
) -> list[str]:
    """Build the shared state sections used by both classifier and planner."""
    sections: list[str] = []

    h_band = _band(core_state.health, 0, core_state.max_health or 100)
    m_band = _band(core_state.money, 0, config.MONEY_MAX)
    s_band = _band(core_state.sanity, 0, 100)

    prev = previous_core_state
    h_dir = _direction(core_state.health, prev.health if prev else None)
    m_dir = _direction(core_state.money, prev.money if prev else None)
    s_dir = _direction(core_state.sanity, prev.sanity if prev else None)

    sections.append("## Current state (quasi)")
    sections.append(f"  health:  {h_band} ({h_dir})")
    sections.append(f"  money:   {m_band} ({m_dir})")
    sections.append(f"  sanity:  {s_band} ({s_dir})")
    sections.append(f"  depth:   {core_state.depth},  act: {core_state.act}")

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
        )[:config.THEME_TOP_N]
        theme_str = ", ".join(f"{t}×{n}" for t, n in top_themes)
        sections.append(f"  dominant themes: {theme_str}")

    if run_memory.important_incidents:
        recent = run_memory.important_incidents[-config.INCIDENT_HISTORY_N:]
        sections.append("\n## Recent incidents")
        for inc in recent:
            sections.append(f"  - {inc}")

    if run_memory.recent_shocks:
        sections.append("\n## Recent destabilizing choices")
        for shock in run_memory.recent_shocks[-config.SHOCK_HISTORY_N:]:
            sections.append(
                f"  - [{shock.scene_type}] option={shock.option_id}"
                f"  sanity={shock.sanity_delta}"
            )

    if waypoint_history:
        sections.append(f"\n## Waypoint trajectory ({len(waypoint_history)} completed)")
        for summary in waypoint_history[-config.WAYPOINT_HISTORY_N:]:
            flags = ", ".join(summary.important_flags) if summary.important_flags else "none"
            sections.append(
                f"  [{summary.waypoint_type}] depth={summary.depth}"
                f"  sanity_delta={summary.sanity_delta}  flags={flags}"
            )
    else:
        sections.append("\n## Waypoint trajectory\n  Run just started — no waypoints completed yet.")

    if current_waypoint_memory is not None and current_waypoint_memory.choices_made:
        sections.append("\n## Active waypoint so far (partial)")
        sections.append(
            f"  waypoint={current_waypoint_memory.waypoint_id} type={current_waypoint_memory.waypoint_type}"
            f" depth={current_waypoint_memory.depth}"
        )
        sections.append(
            f"  encounters_resolved={len(current_waypoint_memory.choices_made)}"
            f" sanity_lost={current_waypoint_memory.sanity_lost_in_node}"
        )
        if current_waypoint_memory.important_flags:
            sections.append(
                "  active flags: "
                + ", ".join(current_waypoint_memory.important_flags[-4:])
            )
        for choice in current_waypoint_memory.choices_made[-config.CHOICE_HISTORY_N:]:
            flags = ", ".join(choice.local_flags) if choice.local_flags else "none"
            sections.append(
                f"  - [{choice.scene_type}] option={choice.player_choice or 'unknown'}"
                f" sanity={choice.sanity_delta} flags={flags}"
            )

    if run_memory.a1.entries:
        sections.append("\n## Scene history (M1 — last 3 nodes)")
        for line in run_memory.a1.to_prompt_lines(n=config.A1_ENTRY_N):
            sections.append(line)

    return sections


def _effect_calibration(core_state: CoreStateView) -> str:
    """Derive per-resource effect delta guidance from current tendency bands.

    C2 sees tendency bands, not exact integers. This section translates bands
    into recommended delta ranges so effects stay proportional to actual state.
    """
    max_h = core_state.max_health or 100
    h_band = _band(core_state.health, 0, max_h)
    m_band = _band(core_state.money, 0, config.MONEY_MAX)
    s_band = _band(core_state.sanity, 0, 100)

    # Health: more room to lose when high, more room to gain when low
    h_loss = {"very_low": -5, "low": -8, "moderate": -12, "high": -18, "very_high": -25}.get(h_band, -12)
    h_gain = {"very_low": 15, "low": 12, "moderate": 8, "high": 5, "very_high": 3}.get(h_band, 8)

    # Money: symmetric-ish but avoid wiping out a broke character
    m_loss = {"very_low": -1, "low": -2, "moderate": -4, "high": -6, "very_high": -8}.get(m_band, -4)
    m_gain = 8

    # Sanity: fragile characters shouldn't lose much more; healthy ones can absorb more
    s_loss = {"very_low": -5, "low": -8, "moderate": -12, "high": -16, "very_high": -20}.get(s_band, -10)
    s_gain = {"very_low": 10, "low": 8, "moderate": 5, "high": 3, "very_high": 3}.get(s_band, 5)

    return (
        f"\n## Effect delta calibration (calibrate h/m/s to current state)\n"
        f"  h (health  {h_band}/{max_h}): [{h_loss}, +{h_gain}]  — reserve extremes for pivotal options\n"
        f"  m (money   {m_band}):         [{m_loss}, +{m_gain}]\n"
        f"  s (sanity  {s_band}/100): [{s_loss}, +{s_gain}]  — fragile sanity → smaller losses"
    )


def build_classifier_input(
    core_state: CoreStateView,
    run_memory: RunMemory,
    waypoint_history: list[WaypointSummary],
    previous_core_state: CoreStateView | None = None,
    current_waypoint_memory: WaypointMemory | None = None,
) -> str:
    """Build the input sent to the M2 arc-state classifier (Claude).

    Contains only mechanical game state — no planning request.
    The classifier's job is purely structural: pick the best-matching T2 cache entry.
    """
    sections = _build_state_sections(
        core_state,
        run_memory,
        waypoint_history,
        previous_core_state,
        current_waypoint_memory=current_waypoint_memory,
    )
    sections.append(_effect_calibration(core_state))
    sections.append("\nClassify the arc state that best matches the current game state above.")
    return "\n".join(sections)


def build_quasi_description(
    core_state: CoreStateView,
    run_memory: RunMemory,
    waypoint_history: list[WaypointSummary],
    *,
    target_node_id: str,
    encounter_count: int,
    previous_core_state: CoreStateView | None = None,
    current_waypoint_memory: WaypointMemory | None = None,
) -> str:
    """Build the user-message payload sent to Slow Core (dynamic path).

    Args:
        core_state:           Current precise state after the last node.
        run_memory:           Long-lived run memory (shocks, themes, mood).
        waypoint_history:         Ordered list of WaypointSummary from completed nodes.
        target_node_id:       The node ID Slow Core should plan content for.
        encounter_count:    How many encounters to generate for that node.
        previous_core_state:  State before the last node — used for direction signals.
    """
    sections = _build_state_sections(
        core_state,
        run_memory,
        waypoint_history,
        previous_core_state,
        current_waypoint_memory=current_waypoint_memory,
    )

    sections.append(
        f"\n## Your task\n"
        f"Plan content for node '{target_node_id}'.\n"
        f"Generate exactly {encounter_count} encounter(s).\n"
        f"Each encounter must fit the current state and narrative trajectory above.\n"
        f"Use tendency language only — no exact numbers in scene_concept or sanity_axis.\n"
        f"Call plan_node_content with your plan."
    )

    return "\n".join(sections)
