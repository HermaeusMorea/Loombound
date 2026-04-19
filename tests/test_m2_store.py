import json

from src.t2.memory.a2_store import RuntimeTableStore


def test_m2_store_loads_node_keyed_scene_skeletons(tmp_path) -> None:
    path = tmp_path / "scene_skeletons.json"
    path.write_text(
        json.dumps(
            [
                {
                    "waypoint_id": "ruined_market",
                    "waypoint_type": "market",
                    "label": "Ruined Market",
                    "map_blurb": "Ash merchants linger under torn awnings.",
                    "encounters": [
                        {
                            "scene_type": "market",
                            "scene_concept": "A half-collapsed bazaar still trades in embers.",
                            "sanity_axis": "Need versus disgust.",
                            "options": [
                                {
                                    "option_id": "buy_ember_salt",
                                    "intent": "You trade for a pouch of ember salt.",
                                    "tags": ["trade"],
                                    "effects": {"money_delta": -1},
                                }
                            ],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    store = RuntimeTableStore()
    store.load_scene_skeletons(path)

    node = store.lookup_waypoint("ruined_market")
    assert node is not None
    assert node.waypoint_type == "market"
    assert node.encounters[0].scene_type == "market"
    assert node.encounters[0].options[0]["option_id"] == "buy_ember_salt"
