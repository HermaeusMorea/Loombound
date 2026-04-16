"""Slow Core client — remote LLM planner.

Receives a quasi description of current run state (built by Collector) and
produces a NodeSeedPack: structured plans for all arbitrations in one future node.

Supported providers
-------------------
  anthropic   — claude-opus-4-6 via Anthropic SDK (default)
                Prompt caching and adaptive thinking available.
  openai      — GPT-4o or any model via OpenAI SDK
  qwen        — 通义千问 via DashScope OpenAI-compatible endpoint
  <any>       — Any OpenAI-compatible endpoint via base_url + api_key

All providers use the same tool-use interface (plan_node_content).
Anthropic-specific features (cache_control, thinking) are silently skipped
for non-Anthropic providers.
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field

import anthropic

from .types import (
    ArbitrationOptionSeed,
    ArbitrationSeed,
    NodeSeedPack,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SlowCoreError(Exception):
    """Raised when Slow Core fails to produce a valid NodeSeedPack."""


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

# Known OpenAI-compatible providers: (default_model, base_url, api_key_env_var)
_PROVIDERS: dict[str, tuple[str, str, str]] = {
    "openai":   ("gpt-4o",        "https://api.openai.com/v1",                             "OPENAI_API_KEY"),
    "qwen":     ("qwen-plus",     "https://dashscope.aliyuncs.com/compatible-mode/v1",     "DASHSCOPE_API_KEY"),
    "deepseek": ("deepseek-chat", "https://api.deepseek.com/v1",                            "DEEPSEEK_API_KEY"),
}


def default_model_for(provider: str) -> str:
    """Return the default model name for a given provider slug."""
    if provider == "anthropic":
        return "claude-opus-4-6"
    if provider in _PROVIDERS:
        return _PROVIDERS[provider][0]
    return ""


def api_key_env_for(provider: str) -> str:
    """Return the environment variable name that holds the API key for provider."""
    if provider == "anthropic":
        return "ANTHROPIC_API_KEY"
    if provider in _PROVIDERS:
        return _PROVIDERS[provider][2]
    return "SLOW_CORE_API_KEY"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SlowCoreConfig:
    # Provider slug: "anthropic" | "openai" | "qwen" | "deepseek" | custom
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    # OpenAI-compatible base URL (ignored for anthropic provider).
    # Falls back to the provider registry default if None.
    base_url: str | None = None
    max_tokens: int = 8192
    # Anthropic-only: enable adaptive thinking (ignored for other providers)
    adaptive_thinking: bool = False
    # Options per arbitration
    min_options: int = 2
    max_options: int = 4
    api_key: str | None = None
    # Output language hint passed to the planner: "en" or "zh"
    lang: str = "en"
    # Campaign tone/setting description injected into every user message.
    # If None, no tone hint is sent and the model uses its own judgement.
    tone: str | None = None


# ---------------------------------------------------------------------------
# System prompt (stable — cached across calls via cache_control ephemeral)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a content planner for a text-adventure roguelite. \
Your sole job is to call plan_node_content exactly once per user message, producing \
a single ArbitrationSeed that the game's Fast Core will expand into full scene text.

─── TONE & SETTING ──────────────────────────────────────────────────────────
The campaign's tone and setting are provided at the top of each user message under \
"Campaign tone". Adapt ALL narrative fields to match that tone exactly — vocabulary, \
imagery, genre conventions, and atmosphere. If no tone is specified, infer it from \
the node trajectory and quasi description. Core principle regardless of setting: \
atmosphere over action, implication over exposition, specific over generic.

─── OUTPUT FIELDS — EXACT SEMANTICS ────────────────────────────────────────
node_theme (string)
  One phrase naming the dominant tension for this node.
  e.g. "mercantile desperation", "archival forbidden knowledge", "threshold crossing"

narrative_direction (string)
  One sentence on where the story arc should push after this node.
  e.g. "Player edges closer to the cult's inner circle, but at a cost to their identity."

scene_type (string)
  Canonical category. Use one of:
    encounter | market | exploration | rest | omen | ritual | investigation | threshold

scene_concept (string)
  1–2 vivid sentences that the Fast Core will expand into full narration. Be SPECIFIC:
  name the location detail, the entity, the sensory hook. This is the most important field.
  BAD:  "The player finds something disturbing."
  GOOD: "A ferryman with salt-white eyes offers passage across the flooded plaza — \
his skiff is too dry for a man who works water all day."

sanity_axis (string)
  One phrase describing the player's psychological state as tendency language only.
  Use relative/qualitative language — NEVER reference stat numbers.
  BAD:  "sanity=3, health=6"
  GOOD: "fraying at the edges", "dangerously over-extended", "grimly composed"

option_id (string)
  snake_case English identifier. e.g. "pay_ferryman", "swim_across", "turn_back"

intent (string)
  One sentence: what the player chooses to do and the immediate narrative consequence.
  Written in second-person present tense.
  e.g. "You hand over the coin; the ferryman's fingers are cold as river clay."

tags (array of strings)
  Thematic classifiers in snake_case. 2–4 tags per option.
  e.g. ["threshold", "cost_money", "trust_unknown"]

effects (object)
  Numeric deltas applied by the game kernel after option selection.
  All fields are optional — omit if zero.
    health_delta:   integer, range [-4, +3]. Physical harm or recovery.
    money_delta:    integer, range [-5, +3]. Coin spent or gained.
    sanity_delta:   integer, range [-4, +2]. Mental cost (usually negative) or stabilisation.
    add_conditions: array of snake_case strings. Status effects added to the player.
      Common conditions: exhausted, marked_by_cult, indebted, haunted, blessed_by_river

─── OPTION DESIGN RULES ────────────────────────────────────────────────────
- Provide 2–4 options per arbitration. Each must have a meaningfully different risk profile.
- At least one option should carry significant sanity cost.
- At least one option should be "safe" but costly in money or health.
- Avoid options that are strictly dominant (better in every way than another option).
- effects integers must be small. Avoid extremes like +10 or -10.
- Do NOT invent stat names beyond the four listed above.

─── WHAT TO AVOID ──────────────────────────────────────────────────────────
- Direct stat references in any narrative field ("health=3", "you have 5 coins")
- Generic, setting-agnostic scene concepts ("you face a difficult choice")
- Options that are identical in intent but differ only in wording
- Anything that breaks the diegetic fourth wall
- Tone drift away from the established campaign setting

Call plan_node_content exactly once. Do not add commentary outside the tool call.
"""


# ---------------------------------------------------------------------------
# Tool schema builder
# ---------------------------------------------------------------------------

def _build_tool_input_schema(cfg: SlowCoreConfig, arbitration_count: int) -> dict:
    """Return the JSON Schema for the plan_node_content tool's input."""
    option_schema = {
        "type": "object",
        "properties": {
            "option_id": {"type": "string"},
            "intent":    {"type": "string"},
            "tags":      {"type": "array", "items": {"type": "string"}},
            "effects": {
                "type": "object",
                "properties": {
                    "health_delta":   {"type": "integer"},
                    "money_delta":    {"type": "integer"},
                    "sanity_delta":   {"type": "integer"},
                    "add_conditions": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
        "required": ["option_id", "intent", "tags", "effects"],
        "additionalProperties": False,
    }

    arbitration_schema = {
        "type": "object",
        "properties": {
            "scene_type":    {"type": "string"},
            "scene_concept": {"type": "string"},
            "sanity_axis":   {"type": "string"},
            "options": {
                "type": "array",
                "items": option_schema,
                "minItems": cfg.min_options,
                "maxItems": cfg.max_options,
            },
        },
        "required": ["scene_type", "scene_concept", "sanity_axis", "options"],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "node_theme":          {"type": "string"},
            "narrative_direction": {"type": "string"},
            "arbitrations": {
                "type": "array",
                "items": arbitration_schema,
                "minItems": arbitration_count,
                "maxItems": arbitration_count,
            },
        },
        "required": ["node_theme", "narrative_direction", "arbitrations"],
        "additionalProperties": False,
    }


def _build_anthropic_tool(cfg: SlowCoreConfig, arbitration_count: int) -> dict:
    return {
        "name": "plan_node_content",
        "description": "One arbitration seed for the target node.",
        "input_schema": _build_tool_input_schema(cfg, arbitration_count),
    }


def _build_openai_tool(cfg: SlowCoreConfig, arbitration_count: int) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "plan_node_content",
            "description": "One arbitration seed for the target node.",
            "parameters": _build_tool_input_schema(cfg, arbitration_count),
        },
    }


# ---------------------------------------------------------------------------
# Shared response-body parser
# ---------------------------------------------------------------------------

def _pack_from_raw(raw: dict, target_node_id: str) -> NodeSeedPack:
    """Build a NodeSeedPack from the already-extracted tool-call input dict."""
    arbs_raw = raw.get("arbitrations", [])
    if isinstance(arbs_raw, str):
        try:
            arbs_raw = _json.loads(arbs_raw)
        except _json.JSONDecodeError:
            arbs_raw = []

    arbitrations = []
    for a in arbs_raw:
        arb = _parse_arbitration(a)
        if arb is not None:
            arbitrations.append(arb)

    return NodeSeedPack(
        target_node_id=target_node_id,
        node_theme=raw.get("node_theme", ""),
        narrative_direction=raw.get("narrative_direction", ""),
        arbitrations=arbitrations,
    )


def _parse_arbitration(raw: dict | str) -> ArbitrationSeed | None:
    """Parse one arbitration from the tool call input.

    Returns None if the item is malformed so the caller can skip it.
    """
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except _json.JSONDecodeError:
            log.warning("SlowCore: skipping arbitration item that is not valid JSON: %r", raw[:80])
            return None

    if not isinstance(raw, dict):
        log.warning("SlowCore: skipping arbitration item of unexpected type %s", type(raw))
        return None

    raw_options = raw.get("options", [])
    options = [
        ArbitrationOptionSeed(
            option_id=opt["option_id"],
            intent=opt["intent"],
            tags=opt.get("tags", []),
            effects=opt.get("effects", {}),
        )
        for opt in raw_options
        if isinstance(opt, dict) and "option_id" in opt and "intent" in opt
    ]
    return ArbitrationSeed(
        scene_type=raw.get("scene_type", "unknown"),
        scene_concept=raw.get("scene_concept", ""),
        sanity_axis=raw.get("sanity_axis", ""),
        options=options,
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SlowCoreClient:
    """Multi-provider Slow Core client that produces NodeSeedPacks.

    Usage:
        # Anthropic (default)
        client = SlowCoreClient()

        # OpenAI-compatible (Qwen, GPT, DeepSeek, …)
        client = SlowCoreClient(SlowCoreConfig(provider="qwen", model="qwen-plus"))

        seed = await client.plan_node(
            quasi_description=collector_text,
            target_node_id="night_market_02",
            arbitration_count=2,
        )
    """

    def __init__(self, config: SlowCoreConfig | None = None) -> None:
        cfg = config or SlowCoreConfig()
        self._cfg = cfg

        if cfg.provider == "anthropic":
            self._anthropic = anthropic.AsyncAnthropic(api_key=cfg.api_key)
            self._openai = None
        else:
            try:
                import openai as _openai_mod
            except ImportError as exc:
                raise ImportError(
                    f"Provider '{cfg.provider}' requires the 'openai' package. "
                    "Install it with: pip install openai"
                ) from exc

            # Resolve base_url from registry if not explicitly set
            base_url = cfg.base_url
            if base_url is None and cfg.provider in _PROVIDERS:
                base_url = _PROVIDERS[cfg.provider][1]

            self._openai = _openai_mod.AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=base_url,
            )
            self._anthropic = None

        log.info(
            "SlowCore: provider=%s model=%s",
            cfg.provider, cfg.model,
        )

    async def plan_node(
        self,
        quasi_description: str,
        target_node_id: str,
        arbitration_count: int = 1,
    ) -> NodeSeedPack:
        """Call the configured LLM to produce a NodeSeedPack for target_node_id."""
        log.debug("SlowCore: planning %d arbitration(s) for node '%s'",
                  arbitration_count, target_node_id)

        if self._cfg.provider == "anthropic":
            return await self._plan_anthropic(
                quasi_description, target_node_id, arbitration_count
            )
        else:
            return await self._plan_openai_compat(
                quasi_description, target_node_id, arbitration_count
            )

    # ------------------------------------------------------------------
    # Anthropic path
    # ------------------------------------------------------------------

    async def _plan_anthropic(
        self,
        quasi_description: str,
        target_node_id: str,
        arbitration_count: int,
    ) -> NodeSeedPack:
        tool = _build_anthropic_tool(self._cfg, arbitration_count)
        thinking_param: dict | anthropic.NotGiven = (
            {"type": "adaptive"} if self._cfg.adaptive_thinking
            else anthropic.NOT_GIVEN
        )

        user_content = _build_user_prefix(self._cfg) + quasi_description

        # cache_control marks the stable prefix for prompt caching.
        # System prompt >1024 tokens → Anthropic caches KV, charges ~10% on re-reads.
        tool["cache_control"] = {"type": "ephemeral"}

        response = await self._anthropic.messages.create(  # type: ignore[union-attr]
            model=self._cfg.model,
            max_tokens=self._cfg.max_tokens,
            thinking=thinking_param,
            system=[{"type": "text", "text": _SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "plan_node_content"},
        )

        u = response.usage
        cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
        cache_created = getattr(u, "cache_creation_input_tokens", 0) or 0
        usage = {
            "input": u.input_tokens,
            "output": u.output_tokens,
            "cache_created": cache_created,
            "cache_read": cache_read,
        }
        log.info(
            "SlowCore[anthropic]: input=%d cache_created=%d cache_read=%d output=%d",
            u.input_tokens, cache_created, cache_read, u.output_tokens,
        )

        # Extract tool-call input from Anthropic response
        for block in response.content:
            if block.type == "tool_use" and block.name == "plan_node_content":
                raw = block.input
                if isinstance(raw, str):
                    try:
                        raw = _json.loads(raw)
                    except _json.JSONDecodeError as exc:
                        raise SlowCoreError(
                            f"Failed to parse tool input JSON: {exc}"
                        ) from exc
                pack = _pack_from_raw(raw, target_node_id)
                pack.usage = usage
                return pack

        raise SlowCoreError(
            f"Anthropic response had no plan_node_content tool call. "
            f"stop_reason={response.stop_reason}, "
            f"content_types={[b.type for b in response.content]}"
        )

    # ------------------------------------------------------------------
    # OpenAI-compatible path  (GPT, Qwen, DeepSeek, …)
    # ------------------------------------------------------------------

    async def _plan_openai_compat(
        self,
        quasi_description: str,
        target_node_id: str,
        arbitration_count: int,
    ) -> NodeSeedPack:
        tool = _build_openai_tool(self._cfg, arbitration_count)
        user_content = _build_user_prefix(self._cfg) + quasi_description

        response = await self._openai.chat.completions.create(  # type: ignore[union-attr]
            model=self._cfg.model,
            max_tokens=self._cfg.max_tokens,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
            tools=[tool],
            tool_choice={"type": "function",
                         "function": {"name": "plan_node_content"}},
        )

        u = response.usage
        usage = {
            "input":         getattr(u, "prompt_tokens", 0),
            "output":        getattr(u, "completion_tokens", 0),
            "cache_created": 0,
            "cache_read":    0,
        }
        log.info(
            "SlowCore[%s]: input=%d output=%d",
            self._cfg.provider, usage["input"], usage["output"],
        )

        # Extract tool-call input from OpenAI-compat response
        msg = response.choices[0].message
        if not msg.tool_calls:
            raise SlowCoreError(
                f"OpenAI-compat response had no tool calls. "
                f"finish_reason={response.choices[0].finish_reason}, "
                f"content={msg.content!r:.200}"
            )

        call = msg.tool_calls[0]
        if call.function.name != "plan_node_content":
            raise SlowCoreError(
                f"Unexpected function name: {call.function.name!r}"
            )

        args_str = call.function.arguments
        try:
            raw = _json.loads(args_str)
        except _json.JSONDecodeError as exc:
            # Some providers (DeepSeek) occasionally produce truncated or
            # slightly malformed JSON in tool arguments. Try to salvage it.
            log.warning(
                "SlowCore[%s]: tool arguments JSON error at char %d — attempting repair",
                self._cfg.provider, exc.pos,
            )
            raw = _repair_json(args_str, exc)

        pack = _pack_from_raw(raw, target_node_id)
        pack.usage = usage
        return pack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repair_json(s: str, exc: _json.JSONDecodeError) -> dict:
    """Best-effort repair of malformed JSON from tool arguments.

    Strategies tried in order:
      1. Truncate at the error position and close all open braces/brackets.
      2. If the string ends mid-value (missing closing quote), strip the tail.
    Raises SlowCoreError if all strategies fail.
    """
    # Strategy 1: close open containers up to the error position
    fragment = s[: exc.pos]
    depth: list[str] = []
    in_string = False
    escape_next = False
    for ch in fragment:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in "{[":
                depth.append("}" if ch == "{" else "]")
            elif ch in "}]":
                if depth:
                    depth.pop()

    # If we're mid-string, close the string first
    suffix = '"' if in_string else ""
    suffix += "".join(reversed(depth))
    candidate = fragment + suffix
    try:
        return _json.loads(candidate)
    except _json.JSONDecodeError:
        pass

    # Strategy 2: try the full string after stripping trailing garbage
    for end in range(len(s) - 1, exc.pos - 1, -1):
        if s[end] in "}]":
            try:
                return _json.loads(s[: end + 1])
            except _json.JSONDecodeError:
                continue

    raise SlowCoreError(
        f"Could not repair malformed tool-argument JSON: {exc.msg} at char {exc.pos}. "
        f"Raw (first 200): {s[:200]!r}"
    )


def _build_user_prefix(cfg: SlowCoreConfig) -> str:
    """Build the stable prefix prepended to every user message."""
    parts: list[str] = []
    if cfg.tone:
        parts.append(f"Campaign tone: {cfg.tone}")
    if cfg.lang == "zh":
        parts.append(
            "IMPORTANT: Write scene_concept, sanity_axis, and all intent fields "
            "in Chinese (中文). option_id and tags remain in English snake_case."
        )
    return ("\n\n".join(parts) + "\n\n") if parts else ""
