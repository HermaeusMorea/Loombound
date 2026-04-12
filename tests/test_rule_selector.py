from src.core.deterministic_kernel import RuleTemplate
from src.core.memory import RunMemory
from src.core.rule_engine import RuleSystem
from src.core.runtime import Arbitration
from src.core.rule_engine import evaluate_rules, select_rule
from src.core.signal_interpretation import build_signals, score_themes


def test_selects_self_preservation_rule_for_risky_crossroads() -> None:
    arbitration = Arbitration.from_dict(
        {
            "context_id": "ctx",
            "decision_type": "crossroads",
            "floor": 4,
            "resources": {"money": 5, "health": 3, "sanity": 4},
            "tags": ["branching_path", "omens"],
            "options": [
                {"option_id": "a", "label": "Open the red door", "tags": ["volatile", "high_risk", "occult"], "metadata": {}},
                {"option_id": "b", "label": "Follow the lantern path", "tags": ["safe", "ordered"], "metadata": {}},
            ],
        },
        owner_kind="run",
        owner_id="test_run",
    )
    rules = [
        RuleTemplate.from_dict(
            {
                "id": "shaken",
                "name": "Shaken",
                "decision_types": ["crossroads"],
                "theme": "self_preservation",
                "priority": 100,
                "max_health": 4,
                "required_context_tags": ["branching_path"],
                "preferred_option_tags": ["safe"],
                "forbidden_option_tags": ["volatile"],
                "sanity_penalty": 2,
            }
        ),
        RuleTemplate.from_dict(
            {
                "id": "clarity",
                "name": "Clarity",
                "decision_types": ["crossroads"],
                "theme": "clarity",
                "priority": 10,
                "required_context_tags": ["branching_path"],
                "preferred_option_tags": ["ordered"],
                "forbidden_option_tags": ["uncertain"],
                "sanity_penalty": 1,
            }
        ),
    ]

    theme_scores = score_themes(arbitration, build_signals(arbitration))
    selected = select_rule(evaluate_rules(arbitration, rules, theme_scores))
    assert selected is not None
    assert selected.rule.id == "shaken"


def test_recent_rule_gets_small_freshness_penalty_when_candidates_tie() -> None:
    arbitration = Arbitration.from_dict(
        {
            "context_id": "ctx_tie",
            "decision_type": "market_offer",
            "floor": 10,
            "resources": {"money": 3, "health": 6, "sanity": 6},
            "tags": ["temptation"],
            "options": [
                {"option_id": "safe", "label": "Safe option", "tags": ["safe"], "metadata": {}},
                {"option_id": "greed", "label": "Greedy option", "tags": ["greedy"], "metadata": {}},
            ],
        },
        owner_kind="run",
        owner_id="test_run",
    )
    rules = [
        RuleTemplate.from_dict(
            {
                "id": "recent_rule",
                "name": "Recent Rule",
                "decision_types": ["market_offer"],
                "theme": "composure",
                "priority": 50,
                "required_context_tags": ["temptation"],
                "preferred_option_tags": ["safe"],
                "forbidden_option_tags": ["greedy"],
                "sanity_penalty": 1,
            }
        ),
        RuleTemplate.from_dict(
            {
                "id": "fresh_rule",
                "name": "Fresh Rule",
                "decision_types": ["market_offer"],
                "theme": "composure",
                "priority": 50,
                "required_context_tags": ["temptation"],
                "preferred_option_tags": ["safe"],
                "forbidden_option_tags": ["greedy"],
                "sanity_penalty": 1,
            }
        ),
    ]

    theme_scores = score_themes(arbitration, build_signals(arbitration))
    evaluations = evaluate_rules(arbitration, rules, theme_scores)
    rule_system = RuleSystem(templates=rules, recently_used_rule_ids=["recent_rule"])
    selected = select_rule(evaluations, rule_system=rule_system, run_memory=RunMemory())
    assert selected is not None
    assert selected.rule.id == "fresh_rule"
