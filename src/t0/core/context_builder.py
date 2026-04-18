"""Helpers that load authored JSON assets into runtime-facing objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.t0.memory import Encounter


class AssetValidationError(ValueError):
    """Raised when an authored asset is valid JSON but invalid runtime input."""


def load_json_asset(path: Path) -> dict:
    """Read one local JSON asset used by the offline prototype."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssetValidationError(f"Asset file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AssetValidationError(f"Invalid JSON in asset {path}: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise AssetValidationError(f"Asset {path} must decode to a JSON object.")
    return payload


def validate_node_asset(payload: dict[str, Any], *, source: Path | None = None) -> dict[str, Any]:
    """Validate the minimum structure required for a node asset."""

    label = _source_label(source)
    _require_string(payload, "node_id", label)
    _require_string(payload, "node_type", label)
    _require_int(payload, "depth", label)

    encounters = payload.get("encounters", [])
    if isinstance(encounters, int):
        # LLM-generated mode: integer declares how many encounters Slow Core should produce.
        if encounters < 0:
            raise AssetValidationError(f"{label} field 'encounters' integer must be >= 0.")
    elif isinstance(encounters, list):
        for index, encounter in enumerate(encounters):
            if not isinstance(encounter, dict):
                raise AssetValidationError(f"{label} encounter #{index + 1} must be an object.")
            _require_string(encounter, "file", f"{label} encounter #{index + 1}")
    else:
        raise AssetValidationError(
            f"{label} field 'encounters' must be a list of file references or an integer count."
        )

    return payload


def validate_arbitration_asset(payload: dict[str, Any], *, source: Path | None = None) -> dict[str, Any]:
    """Validate the minimum structure required for an encounter asset."""

    label = _source_label(source)
    context = payload.get("context")
    if not isinstance(context, dict):
        raise AssetValidationError(f"{label} must contain a 'context' object.")

    _require_string(context, "context_id", f"{label} context")
    _require_int(context, "depth", f"{label} context")

    scene_type = context.get("scene_type", context.get("decision_type"))
    if not isinstance(scene_type, str) or not scene_type.strip():
        raise AssetValidationError(f"{label} context must include a non-empty 'scene_type' or 'decision_type'.")

    options = payload.get("options")
    if not isinstance(options, list) or not options:
        raise AssetValidationError(f"{label} must contain a non-empty 'options' list.")

    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise AssetValidationError(f"{label} option #{index + 1} must be an object.")
        _require_string(option, "option_id", f"{label} option #{index + 1}")
        _require_string(option, "label", f"{label} option #{index + 1}")

    return payload


def load_arbitration(path: Path, *, owner_kind: str = "run", owner_id: str = "loombound") -> Encounter:
    """Build an encounter object from an authored encounter JSON file."""

    payload = validate_arbitration_asset(load_json_asset(path), source=path)
    return Encounter.from_dict(payload, owner_kind=owner_kind, owner_id=owner_id)


def _source_label(source: Path | None) -> str:
    """Render a consistent asset label for validation errors."""

    return f"Asset {source}" if source is not None else "Asset"


def _require_string(payload: dict[str, Any], field_name: str, label: str) -> str:
    """Require one non-empty string field in a JSON object."""

    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise AssetValidationError(f"{label} must include a non-empty '{field_name}'.")
    return value


def _require_int(payload: dict[str, Any], field_name: str, label: str) -> int:
    """Require one integer field in a JSON object."""

    value = payload.get(field_name)
    if not isinstance(value, int):
        raise AssetValidationError(f"{label} must include an integer '{field_name}'.")
    return value
