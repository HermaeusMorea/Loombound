import json

from src.t2.memory.a2_store import RuntimeTableStore, ArcStateEntry


def _arc_row(entry_id: int = 1) -> dict:
    return {
        "entry_id": entry_id,
        "arc_trajectory": "descending",
        "world_pressure": "high",
        "narrative_pacing": "slow",
        "pending_intent": "escape",
    }


def _skeleton_row(waypoint_id: str = "market") -> dict:
    return {
        "waypoint_id": waypoint_id,
        "waypoint_type": "market",
        "label": "Ash Market",
        "map_blurb": "Traders sell ash.",
        "encounters": [
            {
                "scene_type": "market",
                "scene_concept": "A half-collapsed stall.",
                "sanity_axis": "Need vs disgust.",
                "options": [
                    {"option_id": "buy", "intent": "Purchase goods.", "tags": ["trade"], "effects": {"money_delta": -1}}
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# load_arc_state_catalog
# ---------------------------------------------------------------------------

def test_load_arc_state_catalog_parses_entries(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([_arc_row(1), _arc_row(2)]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_arc_state_catalog(path)
    assert len(store.arc_state_catalog) == 2
    assert store.arc_state_catalog[1].arc_trajectory == "descending"


def test_lookup_arc_returns_entry(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([_arc_row(7)]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_arc_state_catalog(path)
    entry = store.lookup_arc(7)
    assert entry is not None
    assert entry.entry_id == 7


def test_lookup_arc_missing_returns_none(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([_arc_row(1)]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_arc_state_catalog(path)
    assert store.lookup_arc(99) is None


# ---------------------------------------------------------------------------
# load_scene_skeletons
# ---------------------------------------------------------------------------

def test_load_scene_skeletons_parses_waypoints(tmp_path) -> None:
    path = tmp_path / "skeletons.json"
    path.write_text(json.dumps([_skeleton_row("market"), _skeleton_row("crossroads")]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_scene_skeletons(path)
    assert len(store.scene_skeletons) == 2


def test_load_scene_skeletons_skips_row_without_waypoint_id(tmp_path) -> None:
    path = tmp_path / "skeletons.json"
    row = _skeleton_row("")
    path.write_text(json.dumps([row]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_scene_skeletons(path)
    assert store.scene_skeletons == {}


def test_lookup_waypoint_returns_skeleton(tmp_path) -> None:
    path = tmp_path / "skeletons.json"
    path.write_text(json.dumps([_skeleton_row("ruins")]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_scene_skeletons(path)
    entry = store.lookup_waypoint("ruins")
    assert entry is not None
    assert entry.encounters[0].scene_type == "market"
    assert entry.encounters[0].options[0]["option_id"] == "buy"


def test_lookup_waypoint_missing_returns_none() -> None:
    store = RuntimeTableStore()
    assert store.lookup_waypoint("nonexistent") is None


# ---------------------------------------------------------------------------
# update / current_id / history
# ---------------------------------------------------------------------------

def test_update_sets_current_id_and_history() -> None:
    store = RuntimeTableStore()
    store.update("wp1", 3)
    assert store.current_id == 3
    assert store.history == [("wp1", 3)]


def test_update_accumulates_history() -> None:
    store = RuntimeTableStore()
    store.update("wp1", 1)
    store.update("wp2", 5)
    assert len(store.history) == 2
    assert store.history[-1] == ("wp2", 5)


# ---------------------------------------------------------------------------
# has_caches
# ---------------------------------------------------------------------------

def test_has_caches_false_when_empty() -> None:
    assert RuntimeTableStore().has_caches() is False


def test_has_caches_true_when_both_loaded(tmp_path) -> None:
    catalog = tmp_path / "catalog.json"
    skeletons = tmp_path / "skeletons.json"
    catalog.write_text(json.dumps([_arc_row()]), encoding="utf-8")
    skeletons.write_text(json.dumps([_skeleton_row()]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_arc_state_catalog(catalog)
    store.load_scene_skeletons(skeletons)
    assert store.has_caches() is True


# ---------------------------------------------------------------------------
# serialization
# ---------------------------------------------------------------------------

def test_arc_state_catalog_json_is_sorted_by_entry_id(tmp_path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([_arc_row(3), _arc_row(1), _arc_row(2)]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_arc_state_catalog(path)
    rows = json.loads(store.arc_state_catalog_json())
    ids = [r["entry_id"] for r in rows]
    assert ids == sorted(ids)


def test_scene_option_index_json_strips_to_id_and_intent(tmp_path) -> None:
    path = tmp_path / "skeletons.json"
    path.write_text(json.dumps([_skeleton_row("market")]), encoding="utf-8")
    store = RuntimeTableStore()
    store.load_scene_skeletons(path)
    rows = json.loads(store.scene_option_index_json())
    assert rows[0]["waypoint_id"] == "market"
    opt = rows[0]["encounters"][0]["options"][0]
    assert "id" in opt
    assert "intent" in opt
    assert "effects" not in opt   # effects stripped
