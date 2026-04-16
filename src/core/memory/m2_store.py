"""M2 memory store — arc-level trajectory state.

Two tables:
  Table A  (data/m2_table_a.json): campaign-agnostic, generated once offline by Claude.
           Contains only the 4 arc-state enum fields + an integer ID.
           Loaded at game startup; placed as a cached prefix in every Claude classifier call.

  Table B  (data/nodes/<campaign_id>/table_b.json): per-campaign, generated offline by DeepSeek.
           Maps each Table A ID to a full ArbitrationSeed (scene_concept, sanity_axis, options).
           Loaded at game startup if present; used as fast lookup during prefetch.

At runtime the M2Classifier (Claude) receives Table A (cached) + current M1+M0 quasi state
and returns a single entry_id. The pipeline then looks up Table B[entry_id] to get the
ArbitrationSeed that Fast Core (gemma3) will expand into display text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Table A row
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class M2Entry:
    """One row of Table A — arc state classification only, no narrative content."""

    entry_id: int
    arc_trajectory: str   # rising | plateau | climax | resolution | pivot
    world_pressure: str   # low | moderate | high | critical
    narrative_pacing: str # slow | steady | accelerating | sprint
    pending_intent: str   # exploration | confrontation | revelation | recovery | transition

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "arc_trajectory": self.arc_trajectory,
            "world_pressure": self.world_pressure,
            "narrative_pacing": self.narrative_pacing,
            "pending_intent": self.pending_intent,
        }


# ---------------------------------------------------------------------------
# Table B row
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class M2SeedEntry:
    """One row of Table B — Table A state + full ArbitrationSeed content (from DeepSeek)."""

    entry_id: int
    m2: M2Entry
    scene_type: str
    scene_concept: str
    sanity_axis: str
    options: list[dict]  # [{option_id, intent, tags, effects}]

    def to_arbitration_seed_dict(self) -> dict:
        """Return a dict compatible with ArbitrationSeed dataclass fields."""
        return {
            "scene_type": self.scene_type,
            "scene_concept": self.scene_concept,
            "sanity_axis": self.sanity_axis,
            "options": self.options,
        }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

@dataclass
class M2Store:
    """Holds Table A, Table B, and the runtime arc classification history."""

    table_a: dict[int, M2Entry] = field(default_factory=dict)
    table_b: dict[int, M2SeedEntry] = field(default_factory=dict)
    current_id: int | None = None
    history: list[tuple[str, int]] = field(default_factory=list)  # [(node_id, m2_id)]

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_table_a(self, path: Path) -> None:
        """Load Table A from JSON. Expected format: list of M2Entry dicts."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self.table_a = {}
        for row in data:
            entry = M2Entry(
                entry_id=int(row["entry_id"]),
                arc_trajectory=row["arc_trajectory"],
                world_pressure=row["world_pressure"],
                narrative_pacing=row["narrative_pacing"],
                pending_intent=row["pending_intent"],
            )
            self.table_a[entry.entry_id] = entry

    def load_table_b(self, path: Path) -> None:
        """Load Table B from JSON. Expected format: list of M2SeedEntry dicts."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self.table_b = {}
        for row in data:
            entry_id = int(row["entry_id"])
            m2_row = row.get("m2", row)  # support flat or nested format
            m2 = M2Entry(
                entry_id=entry_id,
                arc_trajectory=m2_row.get("arc_trajectory", ""),
                world_pressure=m2_row.get("world_pressure", ""),
                narrative_pacing=m2_row.get("narrative_pacing", ""),
                pending_intent=m2_row.get("pending_intent", ""),
            )
            seed = M2SeedEntry(
                entry_id=entry_id,
                m2=m2,
                scene_type=row.get("scene_type", ""),
                scene_concept=row.get("scene_concept", ""),
                sanity_axis=row.get("sanity_axis", ""),
                options=row.get("options", []),
            )
            self.table_b[entry_id] = seed

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def update(self, node_id: str, m2_id: int) -> None:
        """Record the arc classification result for a node."""
        self.current_id = m2_id
        self.history.append((node_id, m2_id))

    def lookup_seed(self, m2_id: int) -> M2SeedEntry | None:
        """Look up Table B by entry_id. Returns None if Table B not loaded or ID missing."""
        return self.table_b.get(m2_id)

    def has_tables(self) -> bool:
        """True if both Table A and Table B are loaded."""
        return bool(self.table_a) and bool(self.table_b)

    def table_a_prompt_json(self) -> str:
        """Serialize Table A to a compact JSON string for use as a cached prompt prefix."""
        rows = [e.to_dict() for e in sorted(self.table_a.values(), key=lambda e: e.entry_id)]
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
