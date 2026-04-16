"""M2 memory store — runtime arc tendencies plus per-node scene skeletons.

Two tables:
  Table A  (data/m2_table_a.json): campaign-agnostic arc-state catalogue.
           Loaded at game startup and cached into every Claude classifier call.

  Table B  (data/nodes/<campaign_id>/table_b.json): per-campaign node skeletons.
           Each row is keyed by campaign node_id and stores one or more scene
           skeletons for that node. These skeletons are later modulated by the
           runtime Table A tendency selected by Claude.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class M2Entry:
    """One row of Table A — arc state classification only, no narrative content."""

    entry_id: int
    arc_trajectory: str
    world_pressure: str
    narrative_pacing: str
    pending_intent: str

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "arc_trajectory": self.arc_trajectory,
            "world_pressure": self.world_pressure,
            "narrative_pacing": self.narrative_pacing,
            "pending_intent": self.pending_intent,
        }


@dataclass(slots=True)
class M2NodeArbitrationSkeleton:
    """One preloaded scene skeleton for a campaign node arbitration slot."""

    scene_type: str
    scene_concept: str
    sanity_axis: str
    options: list[dict]

    def to_seed_dict(self) -> dict:
        return {
            "scene_type": self.scene_type,
            "scene_concept": self.scene_concept,
            "sanity_axis": self.sanity_axis,
            "options": self.options,
        }


@dataclass(slots=True)
class M2NodeSkeletonEntry:
    """One row of Table B — keyed by campaign node_id, not Table A entry_id."""

    node_id: str
    node_type: str
    label: str
    map_blurb: str
    arbitrations: list[M2NodeArbitrationSkeleton] = field(default_factory=list)


@dataclass
class M2Store:
    """Holds Table A, node-keyed Table B, and runtime arc classification history."""

    table_a: dict[int, M2Entry] = field(default_factory=dict)
    table_b: dict[str, M2NodeSkeletonEntry] = field(default_factory=dict)
    current_id: int | None = None
    history: list[tuple[str, int]] = field(default_factory=list)

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
        """Load node-keyed Table B from JSON."""

        data = json.loads(path.read_text(encoding="utf-8"))
        self.table_b = {}
        for row in data:
            node_id = row.get("node_id", "")
            if not node_id:
                continue
            arbitrations = [
                M2NodeArbitrationSkeleton(
                    scene_type=arb.get("scene_type", ""),
                    scene_concept=arb.get("scene_concept", ""),
                    sanity_axis=arb.get("sanity_axis", ""),
                    options=arb.get("options", []),
                )
                for arb in row.get("arbitrations", [])
                if isinstance(arb, dict)
            ]
            self.table_b[node_id] = M2NodeSkeletonEntry(
                node_id=node_id,
                node_type=row.get("node_type", ""),
                label=row.get("label", ""),
                map_blurb=row.get("map_blurb", ""),
                arbitrations=arbitrations,
            )

    def update(self, node_id: str, m2_id: int) -> None:
        """Record the arc classification result for a node."""

        self.current_id = m2_id
        self.history.append((node_id, m2_id))

    def lookup_arc(self, m2_id: int) -> M2Entry | None:
        """Look up a Table A row by entry_id."""

        return self.table_a.get(m2_id)

    def lookup_node(self, node_id: str) -> M2NodeSkeletonEntry | None:
        """Look up a preloaded node skeleton by campaign node_id."""

        return self.table_b.get(node_id)

    def has_tables(self) -> bool:
        """True if both Table A and node-keyed Table B are loaded."""

        return bool(self.table_a) and bool(self.table_b)

    def table_a_prompt_json(self) -> str:
        """Serialize Table A to compact JSON for the Claude classifier prefix."""

        rows = [e.to_dict() for e in sorted(self.table_a.values(), key=lambda e: e.entry_id)]
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    def table_c_prompt_json(self) -> str:
        """Serialize Table B structure (without effects) for the per-campaign cached prefix.

        Table C = Table B stripped to option_id + intent only — Claude uses this to assign
        per-option effect values at runtime without seeing Haiku's placeholder values.
        """
        rows = []
        for node_id, entry in sorted(self.table_b.items()):
            arbs = []
            for idx, arb in enumerate(entry.arbitrations):
                options = [
                    {"id": o.get("option_id", f"opt_{i}"), "intent": o.get("intent", "")}
                    for i, o in enumerate(arb.options)
                ]
                arbs.append({
                    "arb": idx,
                    "scene_type": arb.scene_type,
                    "options": options,
                })
            rows.append({"node_id": node_id, "arbitrations": arbs})
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
