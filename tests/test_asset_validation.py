from pathlib import Path

import pytest

from src.runtime.campaign import choose_index
from src.t0.core import AssetValidationError, validate_arbitration_asset, validate_node_asset


def test_validate_node_asset_requires_arbitration_file() -> None:
    with pytest.raises(AssetValidationError, match="non-empty 'file'"):
        validate_node_asset(
            {
                "node_id": "node_01",
                "node_type": "crossroads",
                "depth": 1,
                "encounters": [{}],
            },
            source=Path("data/nodes/bad.json"),
        )


def test_validate_arbitration_asset_rejects_empty_options() -> None:
    with pytest.raises(AssetValidationError, match="non-empty 'options' list"):
        validate_arbitration_asset(
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
