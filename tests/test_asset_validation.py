from pathlib import Path

import pytest

from src.runtime.saga import choose_index
from src.t0.core import AssetValidationError, validate_encounter_asset, validate_waypoint_asset


def test_validate_waypoint_asset_requires_arbitration_file() -> None:
    with pytest.raises(AssetValidationError, match="non-empty 'file'"):
        validate_waypoint_asset(
            {
                "waypoint_id": "node_01",
                "waypoint_type": "crossroads",
                "depth": 1,
                "encounters": [{}],
            },
            source=Path("data/nodes/bad.json"),
        )


def test_validate_encounter_asset_rejects_empty_options() -> None:
    with pytest.raises(AssetValidationError, match="non-empty 'options' list"):
        validate_encounter_asset(
            {
                "context": {
                    "context_id": "crossroads_01",
                    "scene_type": "crossroads",
                    "depth": 2,
                },
                "options": [],
            },
            source=Path("data/encounters/bad.json"),
        )


def test_choose_index_rejects_empty_choices() -> None:
    with pytest.raises(ValueError, match="empty option list"):
        choose_index("> ", 0)
