"""Helpers that load authored JSON assets into runtime-facing objects."""

from __future__ import annotations

import json
from pathlib import Path

from src.core.runtime import Arbitration


def load_json_asset(path: Path) -> dict:
    """Read one local JSON asset used by the offline prototype."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_arbitration(path: Path, *, owner_kind: str = "run", owner_id: str = "black_archive") -> Arbitration:
    """Build an arbitration object from an authored arbitration JSON file."""
    return Arbitration.from_dict(load_json_asset(path), owner_kind=owner_kind, owner_id=owner_id)
