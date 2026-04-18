"""Runtime helpers for campaign construction and input handling."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.t0.memory import CoreStateView, MetaStateView
from src.runtime.session import Run


REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parents[3]
)


def resolve_asset_path(raw_path: str) -> Path:
    """Resolve authored asset paths relative to the repository root."""

    path = Path(raw_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def make_run(campaign: dict[str, Any]) -> Run:
    """Build the initial runtime run object from a campaign spec."""

    initial_core = campaign["initial_core_state"]
    initial_meta = campaign.get("initial_meta_state", {})
    meta_metadata = initial_meta.get("metadata", {})
    return Run(
        run_id=campaign["campaign_id"],
        core_state=CoreStateView(
            floor=initial_core.get("floor", 1),
            act=initial_core.get("act", 1),
            health=initial_core.get("health"),
            max_health=initial_core.get("max_health"),
            money=initial_core.get("money"),
            sanity=initial_core.get("sanity"),
            scene_type="map",
        ),
        meta_state=MetaStateView(
            sanity=initial_core.get("sanity", 0),
            active_conditions=list(initial_meta.get("active_conditions", [])),
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


def sync_arbitration_resources(run: Run, arbitration: Any) -> None:
    """Refresh arbitration resource fields from the live run state."""

    resources = dict(arbitration.context.resources)
    resources.update(
        {
            "health": run.core_state.health,
            "max_health": run.core_state.max_health,
            "money": run.core_state.money,
            "sanity": run.core_state.sanity,
        }
    )
    arbitration.update_context(resources=resources)
    arbitration.context.core_state_view = replace(run.core_state)
    arbitration.context.meta_state_view = replace(run.meta_state)
