from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.deterministic_kernel import Arbitration


@dataclass(slots=True)
class ObservedOption:
    """One player-facing option observed from native flow."""

    option_id: str
    label: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ObservedScene:
    """Read-only scene snapshot exported from a future native adapter."""

    observation_id: str
    scene_type: str
    floor: int
    act: int = 1
    resources: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    options: list[ObservedOption] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    event_trace: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ObservedScene":
        scene = payload.get("observed_scene", payload)
        return cls(
            observation_id=scene["observation_id"],
            scene_type=scene["scene_type"],
            floor=scene["floor"],
            act=scene.get("act", 1),
            resources=scene.get("resources", {}),
            tags=scene.get("tags", []),
            options=[ObservedOption(**item) for item in scene.get("options", [])],
            metadata=scene.get("metadata", {}),
            event_trace=scene.get("event_trace", []),
        )


def observed_scene_to_arbitration_payload(scene: ObservedScene) -> dict[str, Any]:
    """Convert a read-only observed scene into the project's Arbitration JSON shape."""

    return {
        "arbitration_id": scene.observation_id,
        "context": {
            "context_id": scene.observation_id,
            "scene_type": scene.scene_type,
            "floor": scene.floor,
            "act": scene.act,
            "resources": scene.resources,
            "tags": scene.tags,
            "metadata": {
                **scene.metadata,
                "event_trace": scene.event_trace,
                "adapter_mode": "read_only",
            },
        },
        "options": [
            {
                "option_id": option.option_id,
                "label": option.label,
                "tags": option.tags,
                "metadata": option.metadata,
            }
            for option in scene.options
        ],
        "metadata": {
            "adapter_mode": "read_only",
            "observation_id": scene.observation_id,
        },
    }


def arbitration_from_observed_scene(
    scene: ObservedScene,
    *,
    owner_kind: str = "node",
    owner_id: str = "observed_node",
) -> Arbitration:
    """Build an Arbitration directly from a read-only observed scene."""

    return Arbitration.from_dict(
        observed_scene_to_arbitration_payload(scene),
        owner_kind=owner_kind,
        owner_id=owner_id,
    )


__all__ = [
    "ObservedOption",
    "ObservedScene",
    "observed_scene_to_arbitration_payload",
    "arbitration_from_observed_scene",
]
