from src.core.deterministic_kernel import Arbitration, RuleTemplate
from src.core.rule_engine import evaluate_rules, select_rule
from src.core.signal_interpretation import build_signals, score_themes


def test_selects_low_hp_avoid_elite_rule_for_risky_map() -> None:
    arbitration = Arbitration.from_dict(
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
        },
        owner_kind="run",
        owner_id="test_run",
    )
    rules = [
        RuleTemplate.from_dict(
            {
                "id": "low_hp",
                "name": "Low HP",
                "decision_types": ["map_routing"],
                "theme": "avoid_conflict",
                "priority": 100,
                "max_hp_ratio": 0.45,
                "required_context_tags": ["route_choice"],
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
                "required_context_tags": ["branching_path"],
                "preferred_option_tags": ["ordered"],
                "forbidden_option_tags": ["uncertain"],
                "collapse_penalty": 1,
            }
        ),
    ]

    theme_scores = score_themes(arbitration, build_signals(arbitration))
    selected = select_rule(evaluate_rules(arbitration, rules, theme_scores))
    assert selected is not None
    assert selected.rule.id == "low_hp"
