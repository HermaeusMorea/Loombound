from src.t0.memory import RuleTemplate
from src.t0.memory import Encounter
from src.t0.core import enforce_rule


def test_enforcement_uses_m2_verdict() -> None:
    """M2-assigned verdict on the option is used directly; sanity_penalty comes from rule."""
    encounter = Encounter.from_dict(
        {
            "context_id": "ctx",
            "decision_type": "market_offer",
            "depth": 10,
            "resources": {"money": 3, "health": 6, "sanity": 5},
            "tags": ["temptation"],
            "options": [
                {"option_id": "safe", "label": "Buy lantern oil", "toll": "stable", "tags": [], "metadata": {}},
                {"option_id": "greed", "label": "Buy the whispering idol", "toll": "destabilizing", "tags": [], "metadata": {}},
            ],
        },
        owner_kind="node",
        owner_id="market_node",
    )
    rule = RuleTemplate.from_dict(
        {
            "id": "market_rule",
            "name": "Keep Your Distance",
            "decision_types": ["market_offer"],
            "theme": "detachment",
            "priority": 50,
            "max_money": 4,
            "preferred_option_tags": [],
            "forbidden_option_tags": [],
            "sanity_penalty": 2,
        }
    )

    results = enforce_rule(encounter, rule)
    by_id = {item.option_id: item for item in results}

    assert by_id["safe"].toll == "stable"
    assert by_id["safe"].sanity_cost == 0
    assert by_id["greed"].toll == "destabilizing"
    assert by_id["greed"].sanity_cost == 2


def test_enforcement_defaults_to_stable_without_m2_verdict() -> None:
    """Without M2 verdict, options default to stable with no penalty."""
    encounter = Encounter.from_dict(
        {
            "context_id": "ctx",
            "decision_type": "market_offer",
            "depth": 1,
            "resources": {"money": 5, "health": 8, "sanity": 10},
            "tags": [],
            "options": [
                {"option_id": "opt_a", "label": "Option A", "tags": [], "metadata": {}},
                {"option_id": "opt_b", "label": "Option B", "tags": [], "metadata": {}},
            ],
        },
        owner_kind="node",
        owner_id="test_node",
    )

    results = enforce_rule(encounter, rule=None)
    for item in results:
        assert item.toll == "stable"
        assert item.sanity_cost == 0
