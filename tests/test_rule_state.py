from src.t0.core.rule_state import RuleSystem, WaypointRuleState
from src.t0.memory import RuleTemplate, RuleEvaluation


def _rule(rule_id: str) -> RuleTemplate:
    return RuleTemplate.from_dict({
        "id": rule_id, "name": rule_id, "decision_types": ["crossroads"],
        "theme": "clarity", "priority": 50,
    })


def _eval(rule_id: str, matched: bool = True) -> RuleEvaluation:
    return RuleEvaluation(rule=_rule(rule_id), matched=matched, reasons=[])


# ---------------------------------------------------------------------------
# RuleSystem
# ---------------------------------------------------------------------------

def test_set_templates_replaces_list() -> None:
    rs = RuleSystem()
    rs.set_templates([_rule("a"), _rule("b")])
    assert len(rs.templates) == 2


def test_record_selected_rule_appends_and_counts() -> None:
    rs = RuleSystem()
    rs.record_selected_rule("shaken")
    assert "shaken" in rs.recently_used_rule_ids
    assert rs.rule_use_counts["shaken"] == 1


def test_record_selected_rule_increments_count() -> None:
    rs = RuleSystem()
    rs.record_selected_rule("shaken")
    rs.record_selected_rule("shaken")
    assert rs.rule_use_counts["shaken"] == 2


def test_recently_used_window_capped_at_five() -> None:
    rs = RuleSystem()
    for i in range(7):
        rs.record_selected_rule(f"rule_{i}")
    assert len(rs.recently_used_rule_ids) == 5
    assert rs.recently_used_rule_ids[-1] == "rule_6"


def test_none_rule_id_ignored() -> None:
    rs = RuleSystem()
    rs.record_selected_rule(None)
    assert rs.recently_used_rule_ids == []
    assert rs.rule_use_counts == {}


# ---------------------------------------------------------------------------
# WaypointRuleState
# ---------------------------------------------------------------------------

def test_reset_for_encounter_clears_candidates_and_selection() -> None:
    wrs = WaypointRuleState(available_rule_ids=["a", "b"])
    wrs.candidate_rule_ids = ["a"]
    wrs.selected_rule_id = "a"
    wrs.selection_trace = ["a won"]
    wrs.reset_for_encounter()
    assert wrs.candidate_rule_ids == []
    assert wrs.selected_rule_id is None
    assert wrs.selection_trace == []
    assert wrs.available_rule_ids == ["a", "b"]   # unchanged


def test_record_evaluations_stores_matched_only() -> None:
    wrs = WaypointRuleState()
    wrs.record_evaluations([_eval("a", matched=True), _eval("b", matched=False)])
    assert wrs.candidate_rule_ids == ["a"]


def test_record_selected_rule_sets_id() -> None:
    wrs = WaypointRuleState()
    wrs.record_selected_rule("clarity")
    assert wrs.selected_rule_id == "clarity"


def test_record_selection_trace_copies_list() -> None:
    wrs = WaypointRuleState()
    trace = ["x", "y"]
    wrs.record_selection_trace(trace)
    trace.append("z")   # mutating original should not affect stored trace
    assert wrs.selection_trace == ["x", "y"]
