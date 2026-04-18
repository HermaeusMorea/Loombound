"""Fast Core — local gemma3:4b expansion via ollama.

Takes an EncounterSeed (Slow Core output) and expands it into a complete
encounter JSON dict that passes validate_arbitration_asset.

Expansion targets per encounter:
  context.metadata.scene_summary   — 3-5 atmospheric sentences
  context.metadata.sanity_question — 1 sentence evoking the choice tension
  options[].label                  — 5-10 word display label
  options[].metadata.effects.add_events — 1-2 sentences, causally tied to effects

All other fields (scene_type, floor, tags, numeric effects, add_marks)
are filled deterministically from the seed — no LLM needed for those.

Ollama is called via its native /api/chat endpoint with JSON mode for reliable
structured output. One HTTP call per encounter keeps prompts short and failures
isolated.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from src.t2.core.types import EncounterOptionSeed, EncounterSeed
from src.t0.memory.models import CoreStateView

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class FastCoreConfig:
    model: str = "gemma3:4b"
    base_url: str = "http://localhost:11434"
    # Per-encounter generation timeout (seconds)
    timeout: float = 60.0
    # Max retries on malformed JSON
    max_retries: int = 2
    # Output language: "en" or "zh"
    lang: str = "en"
    # Campaign tone/setting guidance for local expansion.
    tone: str | None = None


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_EN = """\
You are a text writer for a text adventure game.

You receive a scene seed and must expand it into display text. Respond ONLY with valid JSON.
No prose outside the JSON. No markdown fences. The JSON must match the schema exactly.

Tone guidelines:
- Match the campaign tone exactly when one is provided.
- If no campaign tone is provided, infer it from the scene seed instead of inventing a default genre.
- Do not inject Cthulhu, dark fantasy, cyberpunk, or any other stock aesthetic unless the seed or campaign tone implies it.
- Concrete sensory detail beats generic filler.
- If the scene skeleton and the runtime arc tendency conflict, preserve the scene's concrete facts but let the runtime arc tendency control dramatic pressure, pacing, and emotional direction.
- option labels are short action phrases (5-10 words), not descriptions.
- add_events must causally explain what happened as a result of the effects listed.
- Never include specific numeric values in add_events or scene_summary (e.g. do not write "lost 3 health" or "paid 2 coins"). Describe consequences narratively instead.
"""

_SYSTEM_PROMPT_ZH = """\
你是一个文字冒险游戏的文本写手。

你将收到一个场景种子，必须将其展开为显示文本。只输出合法的JSON，不要在JSON外面写任何内容，不要写Markdown代码块。JSON必须严格符合要求的结构。

文字风格要求：
- 如果提供了 campaign tone，必须严格贴合它的类型、氛围、意象和叙述语气。
- 如果没有提供 campaign tone，就从 scene seed 自己推断，不要默认套用固定题材。
- 不要擅自加入克苏鲁、黑暗奇幻、赛博朋克等模板化风格，除非 seed 或 campaign tone 明确要求。
- 多用具体感官细节，少用空泛套话。
- 如果场景骨架和 runtime arc tendency 有冲突，要保留场景的客观事实，但让 runtime arc tendency 主导压力、节奏和情绪方向。
- 选项标签是简短的行动短语（10-20个汉字），不是描述。
- add_events必须从因果上解释所列效果发生的原因。用中文写。
- 绝对不能在 add_events 或 scene_summary 中出现具体数值（例如不要写"失去了3点生命"或"花费了2枚金币"）。用叙述性语言描述后果。
"""


def _system_prompt(cfg: FastCoreConfig) -> str:
    """Build the system prompt for the configured language and campaign tone."""

    prompt = _SYSTEM_PROMPT_ZH if cfg.lang == "zh" else _SYSTEM_PROMPT_EN
    if cfg.tone:
        prompt += f"\n\nCampaign tone: {cfg.tone}"
    return prompt

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(seed: EncounterSeed, core_state: CoreStateView) -> str:
    option_lines: list[str] = []
    for opt in seed.options:
        eff = opt.effects
        parts = []
        if eff.get("health_delta", 0) < 0:
            parts.append("health decreases")
        elif eff.get("health_delta", 0) > 0:
            parts.append("health recovers")
        if eff.get("money_delta", 0) < 0:
            parts.append("money cost")
        elif eff.get("money_delta", 0) > 0:
            parts.append("money gain")
        if eff.get("sanity_delta", 0) < 0:
            parts.append("sanity harm")
        elif eff.get("sanity_delta", 0) > 0:
            parts.append("sanity recovery")
        if eff.get("add_marks"):
            parts.append(f"gains: {', '.join(eff['add_marks'])}")
        eff_str = ", ".join(parts) if parts else "no stat effect"

        option_lines.append(
            f'  option_id: "{opt.option_id}"\n'
            f'  intent: "{opt.intent}"\n'
            f'  tags: {opt.tags}\n'
            f'  effects: {eff_str}'
        )

    options_block = "\n\n".join(option_lines)

    # Build the expected JSON schema as a concrete example
    options_schema = json.dumps(
        [
            {
                "option_id": opt.option_id,
                "label": "<5-10 word label>",
                "add_events": ["<1-2 sentences explaining: " + _effects_hint(opt) + ">"],
            }
            for opt in seed.options
        ],
        indent=2,
    )

    tendency_block = ""
    if seed.tendency:
        tendency_lines = [
            f"{key}: {value}"
            for key, value in seed.tendency.items()
        ]
        tendency_block = (
            "Runtime arc tendency:\n"
            + "\n".join(f"  {line}" for line in tendency_lines)
            + "\n\n"
        )

    return (
        f"Scene concept: {seed.scene_concept}\n"
        f"Sanity axis: {seed.sanity_axis}\n"
        f"Depth: {core_state.depth}, Act: {core_state.act}\n\n"
        f"{tendency_block}"
        f"Options:\n{options_block}\n\n"
        f"Return this JSON structure exactly:\n"
        f"{{\n"
        f'  "scene_summary": "<3-5 atmospheric sentences describing the situation>",\n'
        f'  "sanity_question": "<1 sentence posing the psychological tension>",\n'
        f'  "options": {options_schema}\n'
        f"}}"
    )


def _effects_hint(opt: EncounterOptionSeed) -> str:
    """Build a causal constraint hint for the add_events prompt."""
    eff = opt.effects
    parts = []
    if eff.get("health_delta", 0) < 0:
        parts.append("explain why health decreased")
    if eff.get("health_delta", 0) > 0:
        parts.append("explain why health recovered")
    if eff.get("money_delta", 0) < 0:
        parts.append("explain cost or loss")
    if eff.get("money_delta", 0) > 0:
        parts.append("explain gain")
    if eff.get("sanity_delta", 0) < 0:
        parts.append("explain psychological harm")
    if eff.get("add_marks"):
        conds = ", ".join(eff["add_marks"])
        parts.append(f"explain why condition '{conds}' was acquired")
    return "; ".join(parts) if parts else "describe what happened"


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

async def _call_ollama(
    prompt: str,
    cfg: FastCoreConfig,
    num_predict: int = 1600,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Call ollama's native /api/chat endpoint with JSON mode.

    Returns (parsed_json, usage) where usage has keys prompt_tokens / eval_tokens.
    """
    system_prompt = _system_prompt(cfg)
    url = f"{cfg.base_url}/api/chat"
    body = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.7,
            "num_predict": num_predict,
        },
    }

    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()

    data = resp.json()
    usage: dict[str, int] = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "eval_tokens": data.get("eval_count", 0),
    }
    msg = data.get("message")
    if not isinstance(msg, dict) or "content" not in msg:
        raise ValueError(
            f"Unexpected ollama response structure — keys={list(data.keys())} "
            f"(model not loaded or OOM?)"
        )
    raw_content = msg["content"]
    log.debug("FastCore raw content length=%d", len(raw_content))

    # Strip any reasoning prose before the first '{' (thinking model artifact)
    json_start = raw_content.find("{")
    if json_start < 0:
        raise ValueError(f"No JSON object found in response (len={len(raw_content)})")
    if json_start > 0:
        log.debug("FastCore: stripping %d chars of reasoning prefix", json_start)
    # Also trim after the last '}' to avoid trailing garbage
    json_end = raw_content.rfind("}") + 1
    content = raw_content[json_start:json_end]
    return json.loads(content), usage


# ---------------------------------------------------------------------------
# Assembler — seed + LLM text → full encounter dict
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
        label = text.get("label") or opt_seed.intent  # fallback to intent
        add_events = text.get("add_events") or []
        if isinstance(add_events, str):
            add_events = [add_events]

        # Build effects dict from seed — LLM only contributes add_events text
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
            "tags": [],  # scene-level tags could be added later
            "metadata": {
                "scene_summary": expanded.get("scene_summary", seed.scene_concept),
                "sanity_question": expanded.get("sanity_question", seed.sanity_axis),
                "generated": True,
            },
        },
        "options": options,
        "metadata": {"source": "llm_generated"},
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class FastCoreExpander:
    """Expands EncounterSeeds into full encounter JSON dicts via ollama.

    Usage:
        expander = FastCoreExpander()
        payload = await expander.expand(seed, core_state, encounter_id="gen_01")
        # payload passes validate_arbitration_asset
    """

    def __init__(self, config: FastCoreConfig | None = None) -> None:
        self._cfg = config or FastCoreConfig()

    async def expand(
        self,
        seed: EncounterSeed,
        core_state: CoreStateView,
        encounter_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Expand one EncounterSeed into a complete encounter JSON dict.

        Returns (payload, usage) where usage has keys prompt_tokens / eval_tokens.
        Falls back to a deterministic template if ollama fails after retries.
        """
        arb_id = encounter_id or f"gen_{uuid.uuid4().hex[:8]}"
        prompt = _build_prompt(seed, core_state)

        expanded: dict[str, Any] = {}
        usage: dict[str, int] = {"prompt_tokens": 0, "eval_tokens": 0}
        last_error: Exception | None = None

        # Budget: base 600 + 300 per option to avoid mid-JSON truncation
        num_predict = 600 + len(seed.options) * 300

        for attempt in range(self._cfg.max_retries + 1):
            try:
                expanded, usage = await _call_ollama(prompt, self._cfg, num_predict)
                log.info(
                    "FastCore: attempt %d succeeded for %s (prompt=%d eval=%d)",
                    attempt + 1, arb_id, usage["prompt_tokens"], usage["eval_tokens"],
                )
                break
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError) as exc:
                last_error = exc
                log.warning(
                    "FastCore expand attempt %d/%d failed: %s",
                    attempt + 1, self._cfg.max_retries + 1, exc,
                )

        if not expanded:
            log.error("FastCore: all retries exhausted, using template fallback. error=%s", last_error)
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
            log.info("FastCore: warmup complete, model '%s' loaded.", self._cfg.model)
        except Exception as exc:
            log.warning("FastCore: warmup failed (ollama may not be running): %s", exc)


# ---------------------------------------------------------------------------
# Template fallback (no LLM)
# ---------------------------------------------------------------------------

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
