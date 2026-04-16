import json

from src.core.memory.m2_store import M2Store


def test_m2_store_loads_node_keyed_table_b(tmp_path) -> None:
    path = tmp_path / "table_b.json"
    path.write_text(
        json.dumps(
            [
                {
                    "node_id": "ruined_market",
                    "node_type": "market",
                    "label": "Ruined Market",
                    "map_blurb": "Ash merchants linger under torn awnings.",
                    "arbitrations": [
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

    store = M2Store()
    store.load_table_b(path)

    node = store.lookup_node("ruined_market")
    assert node is not None
    assert node.node_type == "market"
    assert node.arbitrations[0].scene_type == "market"
    assert node.arbitrations[0].options[0]["option_id"] == "buy_ember_salt"
