"""A1 store — Fast Core scene-level tendency context.

Written deterministically after each waypoint ends (no LLM required).
Translates A0 precise values into tendency labels and accumulates
a sliding window of scene history for C2 classifier context.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class A1Entry:
    """Scene-level semantic summary of one completed waypoint."""

    waypoint_id: str
    scene_type: str
    # Resource/pressure state at waypoint exit
    pressure_level: str       # low | moderate | high | critical
    resource_trajectory: str  # recovering | stable | depleting | critical
    # Outcome classification
    outcome_class: str        # stable | turbulent | deepened
    # Dominant narrative theme this waypoint (from RunMemory.theme_counters)
    narrative_thread: str
    depth: int


@dataclass
class A1Store:
    """Sliding-window store of A1 entries, maintained by C1 (Collector)."""

    entries: list[A1Entry] = field(default_factory=list)
    max_entries: int = 10

    def push(self, entry: A1Entry) -> None:
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def recent(self, n: int = 5) -> list[A1Entry]:
        return self.entries[-n:]

    def to_prompt_lines(self, n: int = 3) -> list[str]:
        """Return compact text lines for the last n entries, injected into tendency description."""
        lines: list[str] = []
        for e in self.recent(n):
            lines.append(
                f"  [{e.depth}] {e.scene_type} — {e.outcome_class}, "
                f"pressure={e.pressure_level}, trajectory={e.resource_trajectory}"
                + (f", thread={e.narrative_thread}" if e.narrative_thread else "")
            )
        return lines
