#!/usr/bin/env python3
"""Generate a Loombound campaign.

Step 1: Claude Opus generates the campaign graph (node topology, labels, map_blurbs).
Step 2: Claude Haiku generates T1 cache — scene skeletons for every node (batch, one call).

Both steps run automatically. Use --skip-t1-cache to stop after Step 1.

Usage:
    python -m src.t3.core.generate_campaign "drowned city cult investigation"
    python -m src.t3.core.generate_campaign "lighthouse keeper's descent" --nodes 8
    python -m src.t3.core.generate_campaign "渔村诅咒" --lang zh --nodes 6
    python -m src.t3.core.generate_campaign "solar archaeology" --tone "dirty political thriller"
    python -m src.t3.core.generate_campaign "theme" --provider deepseek
    python -m src.t3.core.generate_campaign "theme" --skip-t1-cache
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from src.t2.core.gen_a1_cache_table import generate_t1_cache_table_step, write_t1_cache_table  # noqa: F401

REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parents[3]
)
_LLM_LOG = REPO_ROOT / "logs" / "llm.md"

# ---------------------------------------------------------------------------
# Provider registry  (name → default_model, base_url, api_key_env)
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, tuple[str, str, str]] = {
    "deepseek": (
        "deepseek-chat",
        "https://api.deepseek.com/v1",
        "DEEPSEEK_API_KEY",
    ),
    "openai": (
        "gpt-4o",
        "https://api.openai.com/v1",
        "OPENAI_API_KEY",
    ),
    "qwen": (
        "qwen-plus",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DASHSCOPE_API_KEY",
    ),
}


def _provider_defaults(provider: str) -> tuple[str, str, str]:
    if provider in _PROVIDERS:
        return _PROVIDERS[provider]
    raise ValueError(
        f"Unknown provider '{provider}'. "
        f"Choose: anthropic, {', '.join(_PROVIDERS)}"
    )


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _md_log(lines: list[str]) -> None:
    _LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
    block = "\n".join(lines) + "\n\n"
    with _LLM_LOG.open("a", encoding="utf-8") as fh:
        fh.write(block)


_OPUS_INPUT_COST  = 5.0  / 1_000_000   # $/token
_OPUS_OUTPUT_COST = 25.0 / 1_000_000
_HAIKU_INPUT_COST  = 0.80 / 1_000_000
_HAIKU_OUTPUT_COST = 4.0  / 1_000_000
_OPUS_CACHE_READ_COST = 0.50 / 1_000_000  # 10% of input


def _opus_cost(inp: int, out: int) -> float:
    return inp * _OPUS_INPUT_COST + out * _OPUS_OUTPUT_COST


def _haiku_cost(inp: int, out: int) -> float:
    return inp * _HAIKU_INPUT_COST + out * _HAIKU_OUTPUT_COST


def _coerce_json(raw: object) -> dict:
    """Normalise tool call output to a plain dict (handles str and Pydantic models)."""
    if isinstance(raw, str):
        return json.loads(raw)
    return json.loads(json.dumps(raw))


def _log_campaign_core_usage(
    *,
    provider: str,
    model: str,
    theme: str,
    node_count: int,
    lang: str,
    tone_hint: str | None,
    worldview_hint: str | None,
    saga_id: str,
    title: str,
    usage_input: int,
    usage_output: int,
) -> None:
    is_opus = "opus" in model.lower()
    cost = _opus_cost(usage_input, usage_output) if is_opus else _haiku_cost(usage_input, usage_output)
    _md_log([
        f"## [{_ts()}] CAMPAIGN CORE RESPONSE — `{saga_id}`",
        f"provider: {provider}",
        f"model: {model}",
        f"theme: {theme}",
        f"title: {title}",
        f"nodes: {node_count}  language: {lang}",
        f"tone: {(tone_hint or '(none)')[:100]}",
        f"tokens — input: {usage_input}  output: {usage_output}",
        f"cost: ${cost:.4f}",
    ])


# ---------------------------------------------------------------------------
# Campaign graph tool schema (Claude Opus)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a campaign designer for a text-adventure roguelite. Your sole job is to call \
create_campaign exactly once with a complete, structurally valid campaign based on the \
theme the user provides. Invent the tone, setting, and genre yourself — do not default \
to any particular aesthetic unless the theme clearly implies one.

─── CAMPAIGN DESIGN RULES ──────────────────────────────────────────────────
NODE GRAPH
- All waypoint_ids referenced in any waypoint's next_waypoints MUST appear as a waypoint_id in your waypoints list.
- start_waypoint_id MUST be one of the waypoint_ids you define.
- At least one waypoint must have next_waypoints: [] (the terminal node — campaign's climax).
- Depth must increase strictly along any path through the graph.
- Prefer branching over linear chains — at least one fork somewhere in the graph.

NODE TYPES  (use exactly one per node)
  crossroads   — pure navigation choice, minimal encounter
  market       — commerce, trade, dubious vendors
  encounter    — something dangerous or ambiguous in the environment
  archive      — information, forbidden knowledge, documents
  ritual       — ceremony, transformation, a turning point
  threshold    — a boundary crossing, a point of no return
  rest         — brief respite (keep encounters low: 1)
  investigation — detective work, evidence, secrets

ARBITRATION COUNT (integer, 1–3 per node)
  1  — brief node, single consequential moment
  2  — standard node, two linked scenes
  3  — major node, prolonged encounter

TONE FIELD
Write a 2–4 sentence description of the campaign's genre, atmosphere, and aesthetic. \
This will be injected into the content generator for every node. Be specific: name the \
genre, the mood, the kind of imagery that should recur. This is the single most \
important field for content coherence.

map_blurb: 1–2 sentences the player sees on the map. Specific and evocative.
intro: 2–3 sentences setting the whole campaign's opening mood.

VERDICT DICTIONARY
Generate 3–6 campaign-specific verdict labels that describe option consequences.
- Always include "stable" (net delta ≥ 0) and "destabilizing" (net delta clearly negative).
- Add 1–4 theme-specific entries that fit your campaign's tone (e.g. "cursed", "exploitative", "honorable", "corrupting").
- Each entry needs a one-line description of the numeric constraints it implies for h/m/s values.
- These labels will be used by the runtime AI to classify options before assigning numbers.

RULES
Generate 3–5 campaign-specific rules that define the psychological logic of this world. \
Each rule is a pattern the protagonist should follow to maintain stability — a discipline, \
a survival heuristic, a moral code forged by this world's specific pressures.
- id: snake_case, descriptive (e.g. "rule_never_open_unmarked_doors")
- name: a short, memorable maxim phrased as guidance ("When the fog thickens, trust the cold")
- theme: one of: self_preservation, composure, clarity, detachment — or invent one that fits
- decision_types: which scene types trigger this rule (crossroads, market, encounter, archive, ritual, threshold, rest, investigation)
- priority: 60–120 (higher = checked first)
- sanity_penalty: integer 0–3 (cost if the rule is violated)
- preferred_option_tags: tags on options this rule favors
- forbidden_option_tags: tags on options this rule forbids
- match (optional): resource bounds or required_context_tags that restrict when the rule fires \
  (max_health, min_health, max_money, min_money, max_sanity, min_sanity, required_context_tags)
Make the rules feel like they were written by someone who survived this world, not a game designer.

NARRATION TABLE
Write atmospheric narration for each of these five rule themes: \
self_preservation, composure, clarity, detachment, neutral.
Each entry has three fields shown to the player after a choice:
- opening  (1–2 sentences, shown BEFORE the choice — sets the psychological frame)
- judgement (1–2 sentences, shown AFTER the choice — quiet observation on what just happened)
- warning   (1 sentence — the sanity cost or mental toll the player should expect)
Ground the text in your specific world: reference its places, factions, imagery, and stakes. \
Write in second person ("You…" / "你…"). Keep each field under 60 words.

Call create_campaign exactly once.
"""

_TOOL = {
    "name": "create_campaign",
    "description": "Output a complete Loombound campaign structure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "saga_id": {
                "type": "string",
                "description": "Unique snake_case ID, e.g. 'drowned_district_act1'",
            },
            "title": {"type": "string"},
            "intro": {"type": "string"},
            "initial_core_state": {
                "type": "object",
                "properties": {
                    "health":     {"type": "integer"},
                    "max_health": {"type": "integer"},
                    "money":      {"type": "integer"},
                    "sanity":     {"type": "integer"},
                    "depth":      {"type": "integer"},
                    "act":        {"type": "integer"},
                },
                "required": ["health", "max_health", "money", "sanity", "depth", "act"],
                "additionalProperties": False,
            },
            "tone": {
                "type": "string",
                "description": (
                    "2–4 sentences describing the campaign's genre, atmosphere, and aesthetic. "
                    "Used by the runtime content generator for every node. Be specific."
                ),
            },
            "start_waypoint_id": {
                "type": "string",
                "description": "Must match one of the node_ids you define.",
            },
            "waypoints": {
                "type": "array",
                "minItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "waypoint_id": {
                            "type": "string",
                            "description": "snake_case, unique within campaign",
                        },
                        "label":      {"type": "string", "description": "Short display name"},
                        "map_blurb":  {"type": "string", "description": "1–2 atmospheric sentences for map screen"},
                        "waypoint_type":  {"type": "string"},
                        "depth":      {"type": "integer", "minimum": 1},
                        "encounter_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                        },
                        "next_waypoints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "node_ids this node leads to. Empty list = terminal.",
                        },
                    },
                    "required": [
                        "waypoint_id", "label", "map_blurb", "waypoint_type",
                        "depth", "encounter_count", "next_waypoints",
                    ],
                    "additionalProperties": False,
                },
            },
            "toll_lexicon": {
                "type": "array",
                "description": (
                    "3–6 campaign-specific verdict labels. "
                    "Must include 'stable' and 'destabilizing'. "
                    "Add theme-specific entries (e.g. 'cursed', 'exploitative')."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id":          {"type": "string", "description": "Short snake_case label, e.g. 'cursed'"},
                        "description": {"type": "string", "description": "One-line numeric constraint, e.g. 'net delta clearly negative'"},
                    },
                    "required": ["id", "description"],
                    "additionalProperties": False,
                },
            },
            "rules": {
                "type": "array",
                "description": "3–5 campaign-specific rules defining this world's psychological logic.",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "id":                    {"type": "string"},
                        "name":                  {"type": "string"},
                        "theme":                 {"type": "string"},
                        "decision_types":        {"type": "array", "items": {"type": "string"}},
                        "priority":              {"type": "integer"},
                        "sanity_penalty":        {"type": "integer"},
                        "preferred_option_tags": {"type": "array", "items": {"type": "string"}},
                        "forbidden_option_tags": {"type": "array", "items": {"type": "string"}},
                        "match": {
                            "type": "object",
                            "properties": {
                                "required_context_tags": {"type": "array", "items": {"type": "string"}},
                                "max_health":  {"type": "integer"},
                                "min_health":  {"type": "integer"},
                                "max_money":   {"type": "integer"},
                                "min_money":   {"type": "integer"},
                                "max_sanity":  {"type": "integer"},
                                "min_sanity":  {"type": "integer"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "required": ["id", "name", "theme", "decision_types", "priority",
                                 "sanity_penalty", "preferred_option_tags", "forbidden_option_tags"],
                    "additionalProperties": False,
                },
            },
            "narration_table": {
                "type": "object",
                "description": (
                    "Per-theme narration drafts grounded in this campaign's specific world. "
                    "Keys: self_preservation, composure, clarity, detachment, neutral."
                ),
                "properties": {
                    theme: {
                        "type": "object",
                        "properties": {
                            "opening":   {"type": "string"},
                            "judgement": {"type": "string"},
                            "warning":   {"type": "string"},
                        },
                        "required": ["opening", "judgement", "warning"],
                        "additionalProperties": False,
                    }
                    for theme in ("self_preservation", "composure", "clarity", "detachment", "neutral")
                },
                "required": ["self_preservation", "composure", "clarity", "detachment", "neutral"],
                "additionalProperties": False,
            },
        },
        "required": ["saga_id", "title", "intro", "tone", "initial_core_state", "start_waypoint_id", "waypoints", "toll_lexicon", "rules", "narration_table"],
        "additionalProperties": False,
    },
}

_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": _TOOL["name"],
        "description": _TOOL["description"],
        "parameters": _TOOL["input_schema"],
    },
}


# ---------------------------------------------------------------------------
# Campaign graph generation — Anthropic
# ---------------------------------------------------------------------------

async def _generate_anthropic(
    theme: str,
    node_count: int,
    lang: str,
    provider: str,
    model: str,
    api_key: str | None,
    tone_hint: str | None = None,
    worldview_hint: str | None = None,
) -> dict:
    client = anthropic.AsyncAnthropic(api_key=api_key)
    user_msg = _build_user_msg(theme, node_count, lang, tone_hint, worldview_hint)

    print(f"  Calling {model} ({node_count} nodes, theme: {theme!r})...")
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "create_campaign"},
    )

    u = response.usage
    print(f"  Usage: input={u.input_tokens}  output={u.output_tokens}  "
          f"(~${_opus_cost(u.input_tokens, u.output_tokens):.4f})")

    for block in response.content:
        if block.type == "tool_use" and block.name == "create_campaign":
            raw = _coerce_json(block.input)
            _log_campaign_core_usage(
                provider=provider, model=model, theme=theme,
                node_count=node_count, lang=lang,
                tone_hint=tone_hint, worldview_hint=worldview_hint,
                saga_id=raw["saga_id"],
                title=raw.get("title", raw["saga_id"]),
                usage_input=u.input_tokens,
                usage_output=u.output_tokens,
            )
            return raw

    raise RuntimeError(
        f"No create_campaign tool call in response. stop_reason={response.stop_reason}"
    )


# ---------------------------------------------------------------------------
# Campaign graph generation — OpenAI-compatible
# ---------------------------------------------------------------------------

async def _generate_openai_compat(
    theme: str,
    node_count: int,
    lang: str,
    provider: str,
    model: str,
    base_url: str,
    api_key: str | None,
    tone_hint: str | None = None,
    worldview_hint: str | None = None,
) -> dict:
    try:
        import openai  # type: ignore
    except ImportError:
        print(
            "Error: 'openai' package required for non-Anthropic providers. "
            "Run: pip install openai",
            file=sys.stderr,
        )
        sys.exit(1)

    client = openai.AsyncOpenAI(api_key=api_key or "dummy", base_url=base_url)
    user_msg = _build_user_msg(theme, node_count, lang, tone_hint, worldview_hint)

    print(f"  Calling {model} via OpenAI-compat ({node_count} nodes, theme: {theme!r})...")
    response = await client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        tools=[_TOOL_OPENAI],
        tool_choice={"type": "function", "function": {"name": "create_campaign"}},
    )

    usage = response.usage
    if usage:
        print(f"  Usage: input={usage.prompt_tokens}  output={usage.completion_tokens}")

    msg = response.choices[0].message
    if msg.tool_calls:
        for tc in msg.tool_calls:
            if tc.function.name == "create_campaign":
                raw = _coerce_json(tc.function.arguments)
                _log_campaign_core_usage(
                    provider=provider, model=model, theme=theme,
                    node_count=node_count, lang=lang,
                    tone_hint=tone_hint, worldview_hint=worldview_hint,
                    saga_id=raw["saga_id"],
                    title=raw.get("title", raw["saga_id"]),
                    usage_input=usage.prompt_tokens if usage else 0,
                    usage_output=usage.completion_tokens if usage else 0,
                )
                return raw

    raise RuntimeError(
        f"No create_campaign tool call in response. "
        f"finish_reason={response.choices[0].finish_reason}"
    )


# ---------------------------------------------------------------------------
# Campaign graph generation — dispatcher
# ---------------------------------------------------------------------------

async def _generate(
    theme: str,
    node_count: int,
    lang: str,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    tone_hint: str | None = None,
    worldview_hint: str | None = None,
) -> dict:
    if provider == "anthropic":
        return await _generate_anthropic(
            theme, node_count, lang, provider, model, api_key,
            tone_hint=tone_hint, worldview_hint=worldview_hint,
        )
    return await _generate_openai_compat(
        theme, node_count, lang, provider, model, base_url or "", api_key,
        tone_hint=tone_hint, worldview_hint=worldview_hint,
    )


def _build_user_msg(
    theme: str,
    node_count: int,
    lang: str,
    tone_hint: str | None = None,
    worldview_hint: str | None = None,
) -> str:
    parts = [
        f"Design a Loombound campaign with exactly {node_count} nodes.",
        f"Theme: {theme}",
    ]
    if tone_hint:
        parts.append(
            "Tone guidance: "
            f"{tone_hint}\nTreat this as a strong creative constraint for genre, mood, imagery, and voice."
        )
    if worldview_hint:
        parts.append(
            "Worldview / setting guidance: "
            f"{worldview_hint}\nUse this as a strong constraint for setting logic, factions, technology or magic assumptions, and recurring motifs."
        )
    parts.append(
        "Use a branching graph structure with at least one fork. "
        "Make sure every waypoint_id in next_waypoints actually exists in your waypoints list. "
        f"The final waypoints list must contain exactly {node_count} unique waypoints."
    )
    if lang == "zh":
        parts.append(
            "Write all narrative text (title, intro, tone, label, map_blurb) in Chinese (中文). "
            "waypoint_id and waypoint_type remain in English snake_case."
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Response normalisation
# ---------------------------------------------------------------------------

def _normalise(data: dict) -> dict:
    nodes = data.get("waypoints", data.get("nodes", []))
    data = dict(data)
    if isinstance(nodes, dict):
        normalised: list[dict] = []
        for node_id, spec in nodes.items():
            if isinstance(spec, dict):
                spec = dict(spec)
                spec.setdefault("waypoint_id", node_id)
                normalised.append(spec)
        data["waypoints"] = normalised
    elif isinstance(nodes, list):
        data["waypoints"] = [n for n in nodes if isinstance(n, dict)]
    data.pop("nodes", None)
    return data


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_graph(
    nodes: list[dict],
    start_node_id: str,
    expected_node_count: int | None = None,
) -> list[str]:
    errors: list[str] = []
    if not nodes:
        errors.append("nodes list is empty — model returned no nodes or wrong format")
        return errors
    bad = [i for i, n in enumerate(nodes) if not isinstance(n, dict)]
    if bad:
        errors.append(f"nodes[{bad}] are not objects — malformed response from model")
        return errors
    node_ids = {n["waypoint_id"] for n in nodes}

    if start_node_id not in node_ids:
        errors.append(f"start_node_id '{start_node_id}' not found in nodes")

    if expected_node_count is not None and len(node_ids) != expected_node_count:
        errors.append(
            f"Expected exactly {expected_node_count} unique nodes, got {len(node_ids)}"
        )

    for node in nodes:
        for ref in node.get("next_waypoints", []):
            if ref not in node_ids:
                errors.append(
                    f"'{node['waypoint_id']}' → '{ref}': referenced node does not exist"
                )

    if not any(not n.get("next_waypoints") for n in nodes):
        errors.append("No terminal nodes (next_nodes: []) — campaign has no ending")

    return errors


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_campaign(data: dict, out_name: str, generation_context: dict | None = None) -> tuple[Path, int]:
    saga_id = data["saga_id"]
    nodes_raw: list[dict] = data["waypoints"]

    campaigns_dir = REPO_ROOT / "data" / "sagas"
    nodes_dir = REPO_ROOT / "data" / "waypoints" / saga_id
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    nodes_dir.mkdir(parents=True, exist_ok=True)  # for t1_cache_table.json

    campaign_nodes: dict = {}
    for node in nodes_raw:
        nid = node["waypoint_id"]
        campaign_nodes[nid] = {
            "label":        node["label"],
            "map_blurb":    node["map_blurb"],
            "waypoint_type":    node["waypoint_type"],
            "depth":        node["depth"],
            "encounters": node["encounter_count"],
            "next_waypoints":   node["next_waypoints"],
        }

    campaign_json = {
        "saga_id":        saga_id,
        "title":              data["title"],
        "intro":              data["intro"],
        "tone":               data.get("tone", ""),
        "initial_core_state": data["initial_core_state"],
        "initial_meta_state": {
            "active_marks": [],
            "metadata": {"major_events": [], "traumas": []},
        },
        "start_waypoint_id": data["start_waypoint_id"],
        "waypoints":         campaign_nodes,
    }
    if generation_context:
        campaign_json["generation_context"] = generation_context

    out_path = campaigns_dir / f"{out_name}.json"
    out_path.write_text(
        json.dumps(campaign_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    toll_lexicon = data.get("toll_lexicon", [])
    if toll_lexicon:
        toll_lexicon_path = campaigns_dir / f"{out_name}_toll_lexicon.json"
        toll_lexicon_path.write_text(
            json.dumps(toll_lexicon, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    rules = data.get("rules", [])
    if rules:
        rules_path = campaigns_dir / f"{out_name}_rules.json"
        rules_path.write_text(
            json.dumps({"rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    narration_table = data.get("narration_table")
    if narration_table:
        narration_path = campaigns_dir / f"{out_name}_narration_table.json"
        narration_path.write_text(
            json.dumps(narration_table, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return out_path, len(nodes_raw)


# ---------------------------------------------------------------------------
# Graph visualiser
# ---------------------------------------------------------------------------

def print_graph(data: dict) -> None:
    nodes = {n["waypoint_id"]: n for n in data["waypoints"]}
    start = data["start_waypoint_id"]
    visited: set[str] = set()

    print("\n  Campaign graph:")

    def _print_node(nid: str, prefix: str, is_last: bool) -> None:
        if nid not in nodes:
            print(f"{prefix}{'└─' if is_last else '├─'} [missing: {nid}]")
            return
        n = nodes[nid]
        connector = "└─" if is_last else "├─"
        tag = " ←START" if nid == start else ""
        arbs = n["encounter_count"]
        print(f"{prefix}{connector} [{n['waypoint_type']}] {nid}  (arb×{arbs}){tag}")
        if nid in visited:
            child_prefix = prefix + ("   " if is_last else "│  ")
            print(f"{child_prefix}  (already shown above)")
            return
        visited.add(nid)
        children = n.get("next_waypoints", [])
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(children):
            _print_node(child, child_prefix, i == len(children) - 1)

    _print_node(start, "  ", True)
    terminal = [n["waypoint_id"] for n in data["waypoints"] if not n.get("next_waypoints")]
    print(f"\n  Terminal node(s): {terminal}")
    total_arbs = sum(n["encounter_count"] for n in data["waypoints"])
    print(f"  Total encounters: {total_arbs}")


# ---------------------------------------------------------------------------
# Step helpers (called from main)
# ---------------------------------------------------------------------------

def _step1_generate_graph(
    args: argparse.Namespace,
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None,
) -> dict:
    """Generate and validate the campaign graph, retrying up to args.retries times.

    Calls sys.exit(1) if all retries fail.
    """
    data: dict | None = None
    for attempt in range(1, args.retries + 1):
        if attempt > 1:
            print(f"\nRetrying (attempt {attempt}/{args.retries})...")
        try:
            data = _normalise(asyncio.run(
                _generate(
                    args.theme, args.nodes, args.lang,
                    provider, model, api_key, base_url,
                    tone_hint=args.tone,
                    worldview_hint=args.worldview,
                )
            ))
        except Exception as exc:
            print(f"Generation failed: {exc}", file=sys.stderr)
            if attempt == args.retries:
                sys.exit(1)
            continue

        errors = validate_graph(data["waypoints"], data["start_waypoint_id"], expected_node_count=args.nodes)
        if errors:
            print(f"\nGraph validation failed (attempt {attempt}):")
            for e in errors:
                print(f"  ✗ {e}")
            if attempt == args.retries:
                print("\nAll retries exhausted.", file=sys.stderr)
                sys.exit(1)
            data = None
            continue

        break

    if data is None:
        sys.exit(1)
    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Generate a Loombound campaign.")
    parser.add_argument(
        "theme",
        nargs="?",
        default="drowned city cult investigation",
        help="Campaign theme (default: 'drowned city cult investigation')",
    )
    parser.add_argument("--nodes", type=int, default=6, metavar="N",
                        help="Exact number of nodes to generate (default: 6)")
    parser.add_argument("--out", default=None, metavar="NAME",
                        help="Output filename stem (default: saga_id from model)")
    parser.add_argument("--lang", choices=["en", "zh"], default="en",
                        help="Language for narrative text (default: en)")
    parser.add_argument(
        "--tone", default=None, metavar="TEXT",
        help="Explicit tone guidance (e.g. 'melancholic solarpunk mystery').",
    )
    parser.add_argument(
        "--worldview", default=None, metavar="TEXT",
        help="Explicit worldview/setting guidance.",
    )
    parser.add_argument("--retries", type=int, default=3,
                        help="Max attempts on graph validation failure (default: 3)")
    parser.add_argument(
        "--skip-t1-cache", action="store_true",
        help="Skip T1 cache generation (campaign graph only).",
    )
    parser.add_argument(
        "--provider", default=None, metavar="PROVIDER",
        help="Campaign graph provider: anthropic (default), deepseek, openai, qwen. "
             "Can also be set via CAMPAIGN_CORE_PROVIDER env var.",
    )
    parser.add_argument(
        "--provider-model", dest="provider_model", default=None, metavar="MODEL",
        help="Override model name for the campaign graph provider. "
             "Can also be set via CAMPAIGN_CORE_MODEL env var.",
    )
    args = parser.parse_args()

    # Resolve campaign graph provider / model
    provider = os.environ.get("CAMPAIGN_CORE_PROVIDER") or args.provider or "anthropic"
    provider_model_override = args.provider_model or os.environ.get("CAMPAIGN_CORE_MODEL")

    if provider == "anthropic":
        default_model = "claude-opus-4-6"
        base_url = None
        api_key_env = "ANTHROPIC_API_KEY"
    else:
        try:
            default_model, base_url, api_key_env = _provider_defaults(provider)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    model = provider_model_override or default_model
    api_key = os.environ.get(api_key_env)
    if not api_key:
        print(
            f"Error: {api_key_env} not set "
            f"(required for provider '{provider}').",
            file=sys.stderr,
        )
        sys.exit(1)

    # Anthropic key is always needed for T1 cache generation (Haiku)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not args.skip_t1_cache and not anthropic_key:
        print(
            "Warning: ANTHROPIC_API_KEY not set — skipping T1 cache generation.\n"
            "Run with --skip-t1-cache to suppress this warning, or add the key to .env.",
            file=sys.stderr,
        )
        args.skip_t1_cache = True

    print(
        f"Generating campaign: '{args.theme}' ({args.nodes} nodes) "
        f"via {provider}/{model}"
    )

    # ── Step 1: generate campaign graph ────────────────────────────────────

    data = _step1_generate_graph(args, provider, model, api_key, base_url)

    print_graph(data)

    out_name = args.out or data["saga_id"]
    generation_context = {
        "theme":          args.theme,
        "language":       args.lang,
        "provider":       provider,
        "model":          model,
        "tone_hint":      args.tone,
        "worldview_hint": args.worldview,
    }
    out_path, node_count = write_campaign(data, out_name, generation_context=generation_context)

    print(f"\n  Written: {out_path} ({node_count} nodes inlined)")

    # ── Step 2: generate T1 cache (Haiku, batched 3 nodes per call) ────────

    if not args.skip_t1_cache:
        generate_t1_cache_table_step(data, node_count, args.lang, anthropic_key)

    print(f"\nCAMPAIGN_ID={data['saga_id']}")
    print(f"CAMPAIGN_PATH={out_path}")
    saga_id = data['saga_id']
    print(f"\nTo play:")
    print(f"  ./loombound run --campaign {saga_id} --lang {args.lang}")


if __name__ == "__main__":
    main()
