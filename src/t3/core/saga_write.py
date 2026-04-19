"""File writing and graph visualisation for Loombound sagas."""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parents[3]
)


def write_saga(data: dict, out_name: str, generation_context: dict | None = None) -> tuple[Path, int]:
    saga_id = data["saga_id"]
    nodes_raw: list[dict] = data["waypoints"]

    sagas_dir = REPO_ROOT / "data" / "sagas"
    nodes_dir = REPO_ROOT / "data" / "waypoints" / saga_id
    sagas_dir.mkdir(parents=True, exist_ok=True)
    nodes_dir.mkdir(parents=True, exist_ok=True)

    saga_nodes: dict = {}
    for waypoint in nodes_raw:
        nid = waypoint["waypoint_id"]
        saga_nodes[nid] = {
            "label":         waypoint["label"],
            "map_blurb":     waypoint["map_blurb"],
            "waypoint_type": waypoint["waypoint_type"],
            "depth":         waypoint["depth"],
            "encounters":    waypoint["encounter_count"],
            "next_waypoints": waypoint["next_waypoints"],
        }

    saga_json = {
        "saga_id":            saga_id,
        "title":              data["title"],
        "intro":              data["intro"],
        "tone":               data.get("tone", ""),
        "initial_core_state": {
            **data["initial_core_state"],
            "health": 100,
            "max_health": 100,
            "sanity": 100,
            "depth": 1,
            "act": 1,
        },
        "initial_meta_state": {
            "active_marks": [],
            "metadata": {"major_events": [], "traumas": []},
        },
        "start_waypoint_id": data["start_waypoint_id"],
        "waypoints":         saga_nodes,
    }
    if generation_context:
        saga_json["generation_context"] = generation_context

    out_path = sagas_dir / f"{out_name}.json"
    out_path.write_text(
        json.dumps(saga_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    toll_lexicon = data.get("toll_lexicon", [])
    if toll_lexicon:
        toll_lexicon_path = sagas_dir / f"{out_name}_toll_lexicon.json"
        toll_lexicon_path.write_text(
            json.dumps(toll_lexicon, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    rules = data.get("rules", [])
    if rules:
        rules_path = sagas_dir / f"{out_name}_rules.json"
        rules_path.write_text(
            json.dumps({"rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    narration_table = data.get("narration_table")
    if narration_table:
        narration_path = sagas_dir / f"{out_name}_narration_table.json"
        narration_path.write_text(
            json.dumps(narration_table, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return out_path, len(nodes_raw)


def print_graph(data: dict) -> None:
    nodes = {n["waypoint_id"]: n for n in data["waypoints"]}
    start = data["start_waypoint_id"]
    visited: set[str] = set()

    print("\n  Saga graph:")

    def _print_waypoint(nid: str, prefix: str, is_last: bool) -> None:
        if nid not in nodes:
            print(f"{prefix}{'└─' if is_last else '├─'} [missing: {nid}]")
            return
        n = nodes[nid]
        connector = "└─" if is_last else "├─"
        tag = " ←START" if nid == start else ""
        arbs = n["encounter_count"]
        print(f"{prefix}{connector} [{n['waypoint_type']}] {nid}  (arb×{arbs}){tag}")
        if nid in visited:
            child_prefix = prefix + ("   " if is_last else "│  ")
            print(f"{child_prefix}  (already shown above)")
            return
        visited.add(nid)
        children = n.get("next_waypoints", [])
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(children):
            _print_waypoint(child, child_prefix, i == len(children) - 1)

    _print_waypoint(start, "  ", True)
    terminal = [n["waypoint_id"] for n in data["waypoints"] if not n.get("next_waypoints")]
    print(f"\n  Terminal waypoint(s): {terminal}")
    total_arbs = sum(n["encounter_count"] for n in data["waypoints"])
    print(f"  Total encounters: {total_arbs}")
