"""C0 logic: enforcement, rule engine, signal interpretation, state adapter, presentation."""

from .enforcement import enforce_rule
from .effects import apply_option_effects
from .rule_state import WaypointRuleState, RuleSystem
from .signals import build_signals
from .context_builder import (
    AssetValidationError, load_encounter, load_json_asset,
    validate_encounter_asset, validate_waypoint_asset,
)

__all__ = [
    "enforce_rule", "apply_option_effects",
    "WaypointRuleState", "RuleSystem",
    "build_signals",
    "AssetValidationError", "load_encounter", "load_json_asset",
    "validate_encounter_asset", "validate_waypoint_asset",
]


def evaluate_rule(*args, **kwargs):
    from .rule_matcher import evaluate_rule as _f
    return _f(*args, **kwargs)


def evaluate_rules(*args, **kwargs):
    from .rule_matcher import evaluate_rules as _f
    return _f(*args, **kwargs)


def select_rule(*args, **kwargs):
    from .rule_selector import select_rule as _f
    return _f(*args, **kwargs)


def build_selection_trace(*args, **kwargs):
    from .rule_selector import build_selection_trace as _f
    return _f(*args, **kwargs)


from .cli import (
    pause, render_encounter_view, render_choices, render_input_panel,
    render_map_hud, render_node_header, render_result, render_run_complete,
    render_run_intro, render_state_panel,
)
