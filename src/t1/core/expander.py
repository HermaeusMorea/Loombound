"""C1 expander — EncounterSeed → full encounter JSON + narration rewrite."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import json

import httpx

from src.t1.core.ollama import C1Config, call_ollama
from src.t1.core.prompts import build_expand_prompt, system_prompt
from src.t2.core.types import EncounterSeed
from src.t0.memory.models import CoreStateView

log = logging.getLogger(__name__)


class C1Expander:
    """Expands EncounterSeeds into full encounter JSON dicts via ollama (qwen2.5:7b).

    Usage:
        expander = C1Expander()
        payload, usage = await expander.expand(seed, core_state)
    """

    def __init__(self, config: C1Config | None = None) -> None:
        self._cfg = config or C1Config()

    async def expand(
        self,
        seed: EncounterSeed,
        core_state: CoreStateView,
        encounter_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Expand one EncounterSeed into a complete encounter JSON dict.

        Returns (payload, usage). Falls back to a deterministic template on failure.
        """
        arb_id = encounter_id or f"gen_{uuid.uuid4().hex[:8]}"
        prompt = build_expand_prompt(seed, core_state)
        sys_prompt = system_prompt(self._cfg)

        expanded: dict[str, Any] = {}
        usage: dict[str, int] = {"prompt_tokens": 0, "eval_tokens": 0}
        last_error: Exception | None = None

        for attempt in range(self._cfg.max_retries + 1):
            try:
                expanded, usage = await call_ollama(prompt, self._cfg, sys_prompt)
                log.info(
                    "C1 expand: attempt %d succeeded for %s (prompt=%d eval=%d)",
                    attempt + 1, arb_id, usage["prompt_tokens"], usage["eval_tokens"],
                )
                break
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as exc:
                last_error = exc
                log.warning(
                    "C1 expand attempt %d/%d failed: %s",
                    attempt + 1, self._cfg.max_retries + 1, exc,
                )

        if not expanded:
            log.error("C1: all retries exhausted, using template fallback. error=%s", last_error)
            expanded = _template_fallback(seed)

        return _assemble(seed, expanded, core_state, arb_id), usage

    async def warmup(self) -> None:
        """Send a minimal request to load the model into VRAM."""
        url = f"{self._cfg.base_url}/api/chat"
        body = {
            "model": self._cfg.model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "options": {"num_predict": 1},
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(url, json=body)
            log.info("C1: warmup complete, model '%s' loaded.", self._cfg.model)
        except Exception as exc:
            log.warning("C1: warmup failed (ollama may not be running): %s", exc)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _assemble(
    seed: EncounterSeed,
    expanded: dict[str, Any],
    core_state: CoreStateView,
    encounter_id: str,
) -> dict[str, Any]:
    """Merge deterministic seed fields with LLM-generated text."""
    option_text: dict[str, dict] = {
        o["option_id"]: o
        for o in expanded.get("options", [])
        if isinstance(o, dict) and "option_id" in o
    }

    options: list[dict[str, Any]] = []
    for opt_seed in seed.options:
        text = option_text.get(opt_seed.option_id, {})
        label = text.get("label") or opt_seed.intent
        add_events = text.get("add_events") or []
        if isinstance(add_events, str):
            add_events = [add_events]

        effects: dict[str, Any] = {}
        for key in ("health_delta", "money_delta", "sanity_delta"):
            val = opt_seed.effects.get(key)
            if val is not None and val != 0:
                effects[key] = val
        if opt_seed.effects.get("add_marks"):
            effects["add_marks"] = list(opt_seed.effects["add_marks"])
        if add_events:
            effects["add_events"] = add_events

        options.append({
            "option_id": opt_seed.option_id,
            "label": label,
            "tags": list(opt_seed.tags),
            "metadata": {"effects": effects},
        })

    return {
        "encounter_id": encounter_id,
        "context": {
            "context_id": encounter_id,
            "scene_type": seed.scene_type,
            "depth": core_state.depth,
            "act": core_state.act,
            "resources": {
                "health": core_state.health,
                "max_health": core_state.max_health,
                "money": core_state.money,
                "sanity": core_state.sanity,
            },
            "tags": [],
            "metadata": {
                "scene_summary": expanded.get("scene_summary", seed.scene_concept),
                "sanity_question": expanded.get("sanity_question", seed.sanity_axis),
                "generated": True,
            },
        },
        "options": options,
        "metadata": {"source": "llm_generated"},
    }


def _template_fallback(seed: EncounterSeed) -> dict[str, Any]:
    """Minimal deterministic expansion used when ollama is unavailable."""
    return {
        "scene_summary": seed.scene_concept,
        "sanity_question": seed.sanity_axis,
        "options": [
            {
                "option_id": opt.option_id,
                "label": opt.intent,
                "add_events": [],
            }
            for opt in seed.options
        ],
    }
