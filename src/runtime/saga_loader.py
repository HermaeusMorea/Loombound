"""Load all per-saga assets from disk into a single bundle."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.shared.llm_utils import REPO_ROOT
from src.t2.memory.a2_store import RuntimeTableStore

SAGAS_DIR = REPO_ROOT / "data" / "sagas"
ARC_STATE_CATALOG_PATH = REPO_ROOT / "data" / "arc_state_catalog.json"


@dataclass
class LoadedSagaBundle:
    saga: dict[str, Any]
    saga_id: str
    rules: list[dict]
    narration_table: dict[str, Any] | None
    toll_lexicon: list[dict]
    tables: RuntimeTableStore = field(default_factory=RuntimeTableStore)


def load_saga_bundle(saga_path: Path) -> LoadedSagaBundle:
    """Load saga JSON and all supporting per-saga assets for a play session."""
    saga = json.loads(saga_path.read_text(encoding="utf-8"))
    saga_id = saga.get("saga_id", "")

    rules_path = SAGAS_DIR / f"{saga_id}_rules.json"
    rules: list[dict] = (
        json.loads(rules_path.read_text(encoding="utf-8"))
        if rules_path.exists() else []
    )

    narration_path = SAGAS_DIR / f"{saga_id}_narration_table.json"
    narration_table: dict[str, Any] | None = (
        json.loads(narration_path.read_text(encoding="utf-8"))
        if narration_path.exists() else None
    )

    lexicon_path = SAGAS_DIR / f"{saga_id}_toll_lexicon.json"
    toll_lexicon: list[dict] = (
        json.loads(lexicon_path.read_text(encoding="utf-8"))
        if lexicon_path.exists() else []
    )

    tables = RuntimeTableStore()
    if ARC_STATE_CATALOG_PATH.exists():
        tables.load_arc_state_catalog(ARC_STATE_CATALOG_PATH)
    skeletons_path = REPO_ROOT / "data" / "waypoints" / saga_id / "scene_skeletons.json"
    if skeletons_path.exists():
        tables.load_scene_skeletons(skeletons_path)

    return LoadedSagaBundle(
        saga=saga,
        saga_id=saga_id,
        rules=rules,
        narration_table=narration_table,
        toll_lexicon=toll_lexicon,
        tables=tables,
    )
