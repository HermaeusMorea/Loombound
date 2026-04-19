"""Runtime narrative table store — arc-state catalog and waypoint scene skeletons.

Two tables:
  Arc-state catalog  (data/arc_state_catalog.json): saga-agnostic arc-state entries.
            Loaded at game startup and injected as a cached prefix into every M2 call.
            Previously referred to as the A2 cache in design docs.

  Scene skeletons  (data/waypoints/<saga_id>/scene_skeletons.json): per-saga skeletons.
            Each row is keyed by saga waypoint_id and stores one or more encounter
            skeletons for that waypoint. Modulated at runtime by the arc state chosen by M2.
            Previously referred to as the A1 cache in design docs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ArcStateEntry:
    """One entry in the arc-state catalog (A2) — classification dimensions only."""

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
class EncounterSkeleton:
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
class WaypointSkeletonEntry:
    """One entry in the scene skeletons table — keyed by saga waypoint_id."""

    waypoint_id: str
    waypoint_type: str
    label: str
    map_blurb: str
    encounters: list[EncounterSkeleton] = field(default_factory=list)


@dataclass
class RuntimeTableStore:
    """Holds the arc-state catalog (A2) and scene skeletons (A1) for runtime use."""

    arc_state_catalog: dict[int, ArcStateEntry] = field(default_factory=dict)
    scene_skeletons: dict[str, WaypointSkeletonEntry] = field(default_factory=dict)
    current_id: int | None = None
    history: list[tuple[str, int]] = field(default_factory=list)

    def load_arc_state_catalog(self, path: Path) -> None:
        """Load arc-state catalog from JSON (list of ArcStateEntry dicts)."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self.arc_state_catalog = {}
        for row in data:
            entry = ArcStateEntry(
                entry_id=int(row["entry_id"]),
                arc_trajectory=row["arc_trajectory"],
                world_pressure=row["world_pressure"],
                narrative_pacing=row["narrative_pacing"],
                pending_intent=row["pending_intent"],
            )
            self.arc_state_catalog[entry.entry_id] = entry

    def load_scene_skeletons(self, path: Path) -> None:
        """Load scene skeletons from JSON (per-waypoint encounter skeletons)."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self.scene_skeletons = {}
        for row in data:
            waypoint_id = row.get("waypoint_id", "")
            if not waypoint_id:
                continue
            encounters = [
                EncounterSkeleton(
                    scene_type=arb.get("scene_type", ""),
                    scene_concept=arb.get("scene_concept", ""),
                    sanity_axis=arb.get("sanity_axis", ""),
                    options=arb.get("options", []),
                )
                for arb in row.get("encounters", [])
                if isinstance(arb, dict)
            ]
            self.scene_skeletons[waypoint_id] = WaypointSkeletonEntry(
                waypoint_id=waypoint_id,
                waypoint_type=row.get("waypoint_type", ""),
                label=row.get("label", ""),
                map_blurb=row.get("map_blurb", ""),
                encounters=encounters,
            )

    def update(self, waypoint_id: str, bearing_id: int) -> None:
        self.current_id = bearing_id
        self.history.append((waypoint_id, bearing_id))

    def lookup_arc(self, bearing_id: int) -> ArcStateEntry | None:
        return self.arc_state_catalog.get(bearing_id)

    def lookup_waypoint(self, waypoint_id: str) -> WaypointSkeletonEntry | None:
        return self.scene_skeletons.get(waypoint_id)

    def has_caches(self) -> bool:
        """True if both arc-state catalog and scene skeletons are loaded."""
        return bool(self.arc_state_catalog) and bool(self.scene_skeletons)

    def arc_state_catalog_json(self) -> str:
        """Serialize arc-state catalog to compact JSON for the M2 classifier cached prefix."""
        rows = [e.to_dict() for e in sorted(self.arc_state_catalog.values(), key=lambda e: e.entry_id)]
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    def scene_option_index_json(self) -> str:
        """Serialize scene skeletons as an option index for the per-saga cached prefix.

        Strips to option_id + intent only — M2 uses this to assign per-option effect
        values without seeing placeholder values.
        """
        rows = []
        for waypoint_id, entry in sorted(self.scene_skeletons.items()):
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
