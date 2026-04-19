"""Load all per-saga assets from disk into a single bundle."""
from __future__ import annotations

import dataclasses
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
    rules: list  # list[RuleTemplate] — dataclass instances, serialisable via asdict
    narration_table: dict[str, Any] | None
    toll_lexicon: list[dict]
    tables: RuntimeTableStore = field(default_factory=RuntimeTableStore)

    def m2_classifier_args(self) -> dict[str, str]:
        """Return keyword arguments for M2Classifier (static cached context tiers)."""
        toll_lexicon_json = json.dumps(self.toll_lexicon, ensure_ascii=False) if self.toll_lexicon else ""
        rules_json = (
            json.dumps({"rules": [dataclasses.asdict(r) for r in self.rules]}, ensure_ascii=False)
            if self.rules else ""
        )
        return {
            "arc_state_catalog_json": self.tables.arc_state_catalog_json(),
            "scene_option_index_json": (
                self.tables.scene_option_index_json() if self.tables.scene_skeletons else ""
            ),
            "toll_lexicon_json": toll_lexicon_json,
            "rules_json": rules_json,
        }


def load_saga_bundle(saga_path: Path) -> LoadedSagaBundle:
    """Load saga JSON and all supporting per-saga assets for a play session."""
    from src.runtime.play_runtime import load_rules as _load_rules

    saga = json.loads(saga_path.read_text(encoding="utf-8"))
    saga_id = saga.get("saga_id", "")

    rules_path = SAGAS_DIR / f"{saga_id}_rules.json"
    rules = _load_rules(rules_path) if rules_path.exists() else []

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
