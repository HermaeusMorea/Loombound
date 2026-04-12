"""Core dataclasses for LLM-generated seed packs, resolved packs, and jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


LLMOutputFamily = Literal["content_pack", "proposal_pack"]
LLMJobKind = Literal[
    "campaign_seed",
    "node_seed",
    "arbitration_seed",
    "rule_seed",
    "narration_seed",
    "meta_summary",
    "rule_bias",
    "effect_suggestion",
]
ProviderMode = Literal["remote_primary", "local_fallback", "hybrid"]
JobStatus = Literal["pending", "ready", "failed", "stale"]


@dataclass(slots=True)
class SeedPack:
    """High-density structured output intended for local expansion."""

    family: LLMOutputFamily
    kind: LLMJobKind
    source: ProviderMode
    payload: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ResolvedPack:
    """Expanded structured output that is ready for adapter validation."""

    family: LLMOutputFamily
    kind: LLMJobKind
    source: ProviderMode
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GenerationJob:
    """One background generation task tracked by runtime."""

    job_id: str
    kind: LLMJobKind
    provider_mode: ProviderMode
    status: JobStatus = "pending"
    input_payload: dict[str, Any] = field(default_factory=dict)
    seed_pack: SeedPack | None = None
    resolved_pack: ResolvedPack | None = None
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
