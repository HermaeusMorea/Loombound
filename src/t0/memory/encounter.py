"""A0 encounter data structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .models import EncounterContext, EncounterResult, CoreStateView, MetaStateView

OwnerKind = Literal["run", "node"]
EncounterStatus = Literal["pending", "evaluated", "applied"]


@dataclass(slots=True)
class Encounter:
    """A judgeable unit owned by either a Run or a Node."""

    encounter_id: str
    owner_kind: OwnerKind
    owner_id: str
    context: EncounterContext
    options: list[dict[str, Any]] = field(default_factory=list)
    selected_option_id: str | None = None
    status: EncounterStatus = "pending"
    result: EncounterResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty_for_owner(
        cls,
        *,
        encounter_id: str,
        owner_kind: OwnerKind,
        owner_id: str,
        scene_type: str,
        depth: int,
        act: int = 1,
        core_state_view: CoreStateView | None = None,
        meta_state_view: MetaStateView | None = None,
    ) -> "Encounter":
        return cls(
            encounter_id=encounter_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            context=EncounterContext.empty(
                context_id=encounter_id,
                scene_type=scene_type,
                depth=depth,
                act=act,
                core_state_view=core_state_view,
                meta_state_view=meta_state_view,
            ),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any], *, owner_kind: OwnerKind, owner_id: str) -> "Encounter":
        context = EncounterContext.from_dict(payload)
        return cls(
            encounter_id=payload.get("encounter_id", context.context_id),
            owner_kind=owner_kind,
            owner_id=owner_id,
            context=context,
            options=[dict(item) for item in payload.get("options", [])],
            metadata=payload.get("metadata", {}),
        )

    def update_context(self, **changes: Any) -> None:
        self.context.update(**changes)

    def load_from_dict(self, payload: dict[str, Any]) -> None:
        context = EncounterContext.from_dict(payload)
        self.encounter_id = payload.get("encounter_id", context.context_id)
        self.context = context
        self.options = [dict(item) for item in payload.get("options", [])]
        self.metadata = payload.get("metadata", {})
        self.selected_option_id = None
        self.result = None
        self.status = "pending"

    def replace_options(self, options: list[dict[str, Any]]) -> None:
        self.options = [dict(item) for item in options]
        if self.selected_option_id and self.get_option(self.selected_option_id) is None:
            self.selected_option_id = None

    def upsert_option(self, option: dict[str, Any]) -> None:
        option_id = option["option_id"]
        for index, current in enumerate(self.options):
            if current["option_id"] == option_id:
                self.options[index] = dict(option)
                return
        self.options.append(dict(option))

    def remove_option(self, option_id: str) -> None:
        self.options = [item for item in self.options if item["option_id"] != option_id]
        if self.selected_option_id == option_id:
            self.selected_option_id = None

    def select_option(self, option_id: str) -> None:
        if self.get_option(option_id) is None:
            raise ValueError(f"Unknown option_id '{option_id}' for encounter '{self.encounter_id}'.")
        self.selected_option_id = option_id

    def get_option(self, option_id: str) -> dict[str, Any] | None:
        for item in self.options:
            if item["option_id"] == option_id:
                return item
        return None

    def set_result(self, result: EncounterResult) -> None:
        self.result = result
        self.status = "evaluated"

    def mark_applied(self) -> None:
        self.status = "applied"
