from src.core.enforcement import enforce_rule
from src.core.models import ChoiceContext, RuleTemplate


def test_enforcement_marks_greedy_choice_as_break_ritual() -> None:
    context = ChoiceContext.from_dict(
        {
            "context_id": "ctx",
            "decision_type": "shop",
            "floor": 10,
            "resources": {"gold": 50, "hp_ratio": 0.5},
            "tags": ["temptation"],
            "options": [
                {"option_id": "safe", "label": "Buy potion", "tags": ["safe", "practical"], "metadata": {}},
                {"option_id": "greed", "label": "Buy relic", "tags": ["greedy", "luxury"], "metadata": {}},
            ],
        }
    )
    rule = RuleTemplate.from_dict(
        {
            "id": "shop_rule",
            "name": "No Ornament",
            "decision_types": ["shop"],
            "theme": "humility",
            "priority": 50,
            "match": {"max_gold": 90},
            "preferred_option_tags": ["practical"],
            "forbidden_option_tags": ["luxury"],
            "collapse_penalty": 2,
        }
    )

    results, collapse_delta = enforce_rule(context, rule)
    by_id = {item.option_id: item for item in results}

    assert by_id["safe"].verdict == "keep_ritual"
    assert by_id["greed"].verdict == "break_ritual"
    assert by_id["greed"].collapse_if_taken == 2
    assert collapse_delta == 2
