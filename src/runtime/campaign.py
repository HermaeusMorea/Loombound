"""Runtime helpers for campaign construction and input handling."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.t0.memory import CoreStateView, MetaStateView, RuleTemplate
from src.t0.core import load_json_asset
from src.runtime.session import Run


REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parents[3]
)


def load_rules(path: Path) -> list[RuleTemplate]:
    """Load per-saga rule data into deterministic rule templates."""
    payload = load_json_asset(path)
    return [RuleTemplate.from_dict(item) for item in payload["rules"]]


def resolve_asset_path(raw_path: str) -> Path:
    """Resolve authored asset paths relative to the repository root."""

    path = Path(raw_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def make_run(saga: dict[str, Any]) -> Run:
    """Build the initial runtime run object from a campaign spec."""

    initial_core = saga["initial_core_state"]
    initial_meta = saga.get("initial_meta_state", {})
    meta_metadata = initial_meta.get("metadata", {})
    return Run(
        run_id=saga["saga_id"],
        core_state=CoreStateView(
            depth=initial_core.get("depth", 1),
            act=initial_core.get("act", 1),
            health=initial_core.get("health"),
            max_health=initial_core.get("max_health"),
            money=initial_core.get("money"),
            sanity=initial_core.get("sanity"),
            scene_type="map",
        ),
        meta_state=MetaStateView(
            sanity=initial_core.get("sanity", 0),
            active_marks=list(initial_meta.get("active_marks", [])),
            narrator_tone=dict(initial_meta.get("narrator_tone", {})),
            theme_bias=dict(initial_meta.get("theme_bias", {})),
            metadata={
                "major_events": list(meta_metadata.get("major_events", [])),
                "traumas": list(meta_metadata.get("traumas", [])),
            },
        ),
    )


def choose_index(prompt: str, count: int) -> int:
    """Read a numbered choice from the CLI."""

    if count <= 0:
        raise ValueError("Cannot choose from an empty option list.")

    while True:
        raw = input(prompt).strip().lower()
        if raw in {"q", "quit", "exit"}:
            raise KeyboardInterrupt
        if raw.isdigit():
            value = int(raw)
            if 1 <= value <= count:
                return value - 1
        print("Enter a valid number or q to quit.")


def sync_encounter_resources(run: Run, encounter: Any) -> None:
    """Refresh encounter resource fields from the live run state."""

    resources = dict(encounter.context.resources)
    resources.update(
        {
            "health": run.core_state.health,
            "max_health": run.core_state.max_health,
            "money": run.core_state.money,
            "sanity": run.core_state.sanity,
        }
    )
    encounter.update_context(resources=resources)
    encounter.context.core_state_view = replace(run.core_state)
    encounter.context.meta_state_view = replace(run.meta_state)
