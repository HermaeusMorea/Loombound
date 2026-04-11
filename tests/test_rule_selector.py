from src.core.models import ChoiceContext, RuleTemplate
from src.core.rule_matcher import evaluate_rules
from src.core.rule_selector import select_rule
from src.core.theme_scorer import score_themes
from src.core.signals import build_signals


def test_selects_low_hp_avoid_elite_rule_for_risky_map() -> None:
    context = ChoiceContext.from_dict(
        {
            "context_id": "ctx",
            "decision_type": "map_routing",
            "floor": 4,
            "resources": {"gold": 60, "hp_ratio": 0.30},
            "tags": ["route_choice", "branching_path"],
            "options": [
                {"option_id": "a", "label": "Elite path", "tags": ["elite", "high_risk"], "metadata": {}},
                {"option_id": "b", "label": "Safe path", "tags": ["safe", "ordered"], "metadata": {}},
            ],
        }
    )
    rules = [
        RuleTemplate.from_dict(
            {
                "id": "low_hp",
                "name": "Low HP",
                "decision_types": ["map_routing"],
                "theme": "avoid_conflict",
                "priority": 100,
                "match": {"max_hp_ratio": 0.45, "required_context_tags": ["route_choice"]},
                "preferred_option_tags": ["safe"],
                "forbidden_option_tags": ["elite"],
                "collapse_penalty": 2,
            }
        ),
        RuleTemplate.from_dict(
            {
                "id": "order",
                "name": "Order",
                "decision_types": ["map_routing"],
                "theme": "order",
                "priority": 10,
                "match": {"required_context_tags": ["branching_path"]},
                "preferred_option_tags": ["ordered"],
                "forbidden_option_tags": ["uncertain"],
                "collapse_penalty": 1,
            }
        ),
    ]

    theme_scores = score_themes(context, build_signals(context))
    selected = select_rule(evaluate_rules(context, rules, theme_scores))
    assert selected is not None
    assert selected.rule.id == "low_hp"

