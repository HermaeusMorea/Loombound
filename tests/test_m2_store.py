import json

from src.t2.memory.a2_store import A2Store


def test_m2_store_loads_node_keyed_a1_cache_table(tmp_path) -> None:
    path = tmp_path / "a1_cache_table.json"
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

    store = A2Store()
    store.load_a1_cache_table(path)

    node = store.lookup_waypoint("ruined_market")
    assert node is not None
    assert node.waypoint_type == "market"
    assert node.encounters[0].scene_type == "market"
    assert node.encounters[0].options[0]["option_id"] == "buy_ember_salt"
