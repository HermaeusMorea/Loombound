from __future__ import annotations

from pathlib import Path

from src.t0.memory import RuleTemplate
from src.t0.core import load_json_asset


def load_rules(path: Path) -> list[RuleTemplate]:
    """Load authored rule data into deterministic rule templates."""
    payload = load_json_asset(path)
    return [RuleTemplate.from_dict(item) for item in payload["rules"]]


def load_templates(path: Path) -> dict[str, list[str]]:
    """Load narration template data for the optional presentation layer."""
    payload = load_json_asset(path)
    return payload
