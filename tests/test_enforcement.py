from src.core.deterministic_kernel import RuleTemplate
from src.core.runtime import Arbitration
from src.core.enforcement import enforce_rule


def test_enforcement_marks_greedy_choice_as_destabilizing() -> None:
    arbitration = Arbitration.from_dict(
        {
            "context_id": "ctx",
            "decision_type": "market_offer",
            "floor": 10,
            "resources": {"money": 3, "health": 6, "sanity": 5},
            "tags": ["temptation"],
            "options": [
                {"option_id": "safe", "label": "Buy lantern oil", "tags": ["safe", "practical"], "metadata": {}},
                {"option_id": "greed", "label": "Buy the whispering idol", "tags": ["greedy", "luxury", "occult"], "metadata": {}},
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
            "preferred_option_tags": ["practical"],
            "forbidden_option_tags": ["luxury", "occult"],
            "sanity_penalty": 2,
        }
    )

    results, sanity_delta = enforce_rule(arbitration, rule)
    by_id = {item.option_id: item for item in results}

    assert by_id["safe"].verdict == "stable"
    assert by_id["greed"].verdict == "destabilizing"
    assert by_id["greed"].sanity_cost == 2
    assert sanity_delta == 2
