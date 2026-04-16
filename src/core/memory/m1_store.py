"""M1 memory store — Fast Core scene-level quasi context.

M1 is written deterministically after each node ends (no LLM required).
It translates M0 precise values into quasi-precise labels and accumulates
a sliding window of scene history for Slow Core / M2 classifier context.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class M1Entry:
    """Scene-level semantic summary of one completed node."""

    node_id: str
    scene_type: str
    # Resource/pressure state at node exit
    pressure_level: str       # low | moderate | high | critical
    resource_trajectory: str  # recovering | stable | depleting | critical
    # Outcome classification
    outcome_class: str        # stable | turbulent | deepened
    # Dominant narrative theme this node (from RunMemory.theme_counters)
    narrative_thread: str
    floor: int


@dataclass
class M1Store:
    """Sliding-window store of M1 entries, maintained by Fast Core (Collector)."""

    entries: list[M1Entry] = field(default_factory=list)
    max_entries: int = 10

    def push(self, entry: M1Entry) -> None:
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]

    def recent(self, n: int = 5) -> list[M1Entry]:
        return self.entries[-n:]

    def to_prompt_lines(self, n: int = 3) -> list[str]:
        """Return compact text lines for the last n entries, injected into quasi description."""
        lines: list[str] = []
        for e in self.recent(n):
            lines.append(
                f"  [{e.floor}] {e.scene_type} — {e.outcome_class}, "
                f"pressure={e.pressure_level}, trajectory={e.resource_trajectory}"
                + (f", thread={e.narrative_thread}" if e.narrative_thread else "")
            )
        return lines
