"""A2 store — runtime bearing entries plus per-waypoint encounter skeletons.

Two caches:
  A2 cache  (data/a2_cache_table.json): saga-agnostic bearing catalogue.
            Loaded at game startup and cached into every C2 (Haiku) call.

  A1 cache  (data/waypoints/<saga_id>/a1_cache_table.json): per-saga waypoint skeletons.
            Each row is keyed by saga waypoint_id and stores one or more encounter
            skeletons for that waypoint. These skeletons are later modulated by the
            runtime bearing selected by C2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class A2Entry:
    """One entry in the A2 cache — bearing classification only, no narrative content."""

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
class A2WaypointEncounterSkeleton:
    """One preloaded encounter skeleton for a saga waypoint encounter slot."""

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
class A2WaypointSkeletonEntry:
    """One entry in the A1 cache — keyed by saga waypoint_id."""

    waypoint_id: str
    waypoint_type: str
    label: str
    map_blurb: str
    encounters: list[A2WaypointEncounterSkeleton] = field(default_factory=list)


@dataclass
class A2Store:
    """Holds A2 cache, waypoint-keyed A1 cache, and runtime bearing classification history."""

    a2_cache_table: dict[int, A2Entry] = field(default_factory=dict)
    a1_cache_table: dict[str, A2WaypointSkeletonEntry] = field(default_factory=dict)
    current_id: int | None = None
    history: list[tuple[str, int]] = field(default_factory=list)

    def load_a2_cache_table(self, path: Path) -> None:
        """Load A2 cache (bearing palette) from JSON. Expected format: list of A2Entry dicts."""

        data = json.loads(path.read_text(encoding="utf-8"))
        self.a2_cache_table = {}
        for row in data:
            entry = A2Entry(
                entry_id=int(row["entry_id"]),
                arc_trajectory=row["arc_trajectory"],
                world_pressure=row["world_pressure"],
                narrative_pacing=row["narrative_pacing"],
                pending_intent=row["pending_intent"],
            )
            self.a2_cache_table[entry.entry_id] = entry

    def load_a1_cache_table(self, path: Path) -> None:
        """Load A1 cache (waypoint-keyed encounter skeletons) from JSON."""

        data = json.loads(path.read_text(encoding="utf-8"))
        self.a1_cache_table = {}
        for row in data:
            waypoint_id = row.get("waypoint_id", "")
            if not waypoint_id:
                continue
            encounters = [
                A2WaypointEncounterSkeleton(
                    scene_type=arb.get("scene_type", ""),
                    scene_concept=arb.get("scene_concept", ""),
                    sanity_axis=arb.get("sanity_axis", ""),
                    options=arb.get("options", []),
                )
                for arb in row.get("encounters", [])
                if isinstance(arb, dict)
            ]
            self.a1_cache_table[waypoint_id] = A2WaypointSkeletonEntry(
                waypoint_id=waypoint_id,
                waypoint_type=row.get("waypoint_type", ""),
                label=row.get("label", ""),
                map_blurb=row.get("map_blurb", ""),
                encounters=encounters,
            )

    def update(self, waypoint_id: str, bearing_id: int) -> None:
        """Record the bearing classification result for a waypoint."""

        self.current_id = bearing_id
        self.history.append((waypoint_id, bearing_id))

    def lookup_arc(self, bearing_id: int) -> A2Entry | None:
        """Look up an A2 cache entry by entry_id."""

        return self.a2_cache_table.get(bearing_id)

    def lookup_waypoint(self, waypoint_id: str) -> A2WaypointSkeletonEntry | None:
        """Look up an A1 cache entry (waypoint skeleton) by saga waypoint_id."""

        return self.a1_cache_table.get(waypoint_id)

    def has_caches(self) -> bool:
        """True if both A2 cache and A1 cache are loaded."""

        return bool(self.a2_cache_table) and bool(self.a1_cache_table)

    def a2_cache_table_prompt_json(self) -> str:
        """Serialize A2 cache to compact JSON for the C2 classifier prefix."""

        rows = [e.to_dict() for e in sorted(self.a2_cache_table.values(), key=lambda e: e.entry_id)]
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    def a1_cache_table_index_json(self) -> str:
        """Serialize A1 cache structure (without effects) for the per-saga cached prefix.

        A1 option index = A1 cache stripped to option_id + intent only — C2 uses this
        to assign per-option effect values at runtime without seeing placeholder values.
        """
        rows = []
        for waypoint_id, entry in sorted(self.a1_cache_table.items()):
            arbs = []
            for idx, arb in enumerate(entry.encounters):
                options = [
                    {"id": o.get("option_id", f"opt_{i}"), "intent": o.get("intent", "")}
                    for i, o in enumerate(arb.options)
                ]
                arbs.append({
                    "arb": idx,
                    "scene_type": arb.scene_type,
                    "options": options,
                })
            rows.append({"waypoint_id": waypoint_id, "encounters": arbs})
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
