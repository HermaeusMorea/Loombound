"""Provider-level placeholders for remote-primary and local-fallback LLM workflows."""

from __future__ import annotations

from .types import GenerationJob


def run_remote_primary(job: GenerationJob) -> GenerationJob:
    """Placeholder for the expensive remote model that produces seed packs."""

    raise NotImplementedError("Remote-primary LLM provider is not implemented yet.")


def run_local_fallback(job: GenerationJob) -> GenerationJob:
    """Placeholder for the local model that expands or rescues generation."""

    raise NotImplementedError("Local-fallback LLM provider is not implemented yet.")
