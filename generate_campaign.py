#!/usr/bin/env python3
"""Generate a Loombound campaign.

Campaign graph structure is designed by a configurable AI provider (one API call, offline).
Generated node files use  "arbitrations": N  (integer) so that the Slow Core
decides the content for each arbitration at runtime.

Usage:
    python generate_campaign.py "drowned city cult investigation"
    python generate_campaign.py --theme "lighthouse keeper's descent" --nodes 8
    python generate_campaign.py --theme "canal district" --nodes 6 --out act2_campaign
    python generate_campaign.py --lang zh --theme "渔村诅咒" --nodes 6
    python generate_campaign.py "orbital salvage mutiny" --tone "dirty political thriller"
    python generate_campaign.py "solar archaeology" --worldview "post-scarcity sailships between ring habitats"
    python generate_campaign.py "theme" --provider deepseek
    python generate_campaign.py "theme" --provider anthropic:claude-haiku-4-5
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

REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parent
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
    """Return (default_model, base_url, api_key_env) for a known provider."""
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
    """Append a markdown block to logs/llm.md."""

    _LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
    block = "\n".join(lines) + "\n\n"
    with _LLM_LOG.open("a", encoding="utf-8") as fh:
        fh.write(block)


def _log_campaign_core_usage(
    *,
    provider: str,
    model: str,
    theme: str,
    node_count: int,
    lang: str,
    tone_hint: str | None,
    worldview_hint: str | None,
    campaign_id: str,
    title: str,
    usage_input: int,
    usage_output: int,
) -> None:
    """Record one campaign-generation usage block in logs/llm.md."""

    lines = [
        f"## [{_ts()}] CAMPAIGN CORE RESPONSE — `{campaign_id}`",
        f"provider: {provider}",
        f"model: {model}",
        f"theme: {theme}",
        f"node_budget: {node_count}",
        f"language: {lang}",
        f"tone_hint: {tone_hint or '(none)'}",
        f"worldview_hint: {worldview_hint or '(none)'}",
        f"title: {title}",
        f"tokens — input: {usage_input}  output: {usage_output}",
    ]
    _md_log(lines)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a campaign designer for a text-adventure roguelite. Your sole job is to call \
create_campaign exactly once with a complete, structurally valid campaign based on the \
theme the user provides. Invent the tone, setting, and genre yourself — do not default \
to any particular aesthetic unless the theme clearly implies one.

─── CAMPAIGN DESIGN RULES ──────────────────────────────────────────────────
NODE GRAPH
- All node_ids referenced in any node's next_nodes MUST appear as a node_id in your nodes list.
- start_node_id MUST be one of the node_ids you define.
- At least one node must have next_nodes: [] (the terminal node — campaign's climax).
- Floors must increase strictly along any path through the graph.
- Prefer branching over linear chains — at least one fork somewhere in the graph.

NODE TYPES  (use exactly one per node)
  crossroads   — pure navigation choice, minimal arbitration
  market       — commerce, trade, dubious vendors
  encounter    — something dangerous or ambiguous in the environment
  archive      — information, forbidden knowledge, documents
  ritual       — ceremony, transformation, a turning point
  threshold    — a boundary crossing, a point of no return
  rest         — brief respite (keep arbitrations low: 1)
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

Call create_campaign exactly once.
"""

# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

_TOOL = {
    "name": "create_campaign",
    "description": "Output a complete Loombound campaign structure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "campaign_id": {
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
                    "floor":      {"type": "integer"},
                    "act":        {"type": "integer"},
                },
                "required": ["health", "max_health", "money", "sanity", "floor", "act"],
                "additionalProperties": False,
            },
            "tone": {
                "type": "string",
                "description": (
                    "2–4 sentences describing the campaign's genre, atmosphere, and aesthetic. "
                    "Used by the runtime content generator for every node. Be specific."
                ),
            },
            "start_node_id": {
                "type": "string",
                "description": "Must match one of the node_ids you define.",
            },
            "nodes": {
                "type": "array",
                "minItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "snake_case, unique within campaign",
                        },
                        "label":      {"type": "string", "description": "Short display name"},
                        "map_blurb":  {"type": "string", "description": "1–2 atmospheric sentences for map screen"},
                        "node_type":  {"type": "string"},
                        "floor":      {"type": "integer", "minimum": 1},
                        "arbitration_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                        },
                        "next_nodes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "node_ids this node leads to. Empty list = terminal.",
                        },
                    },
                    "required": [
                        "node_id", "label", "map_blurb", "node_type",
                        "floor", "arbitration_count", "next_nodes",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["campaign_id", "title", "intro", "tone", "initial_core_state", "start_node_id", "nodes"],
        "additionalProperties": False,
    },
}


# ---------------------------------------------------------------------------
# OpenAI-compatible tool schema
# ---------------------------------------------------------------------------

_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": _TOOL["name"],
        "description": _TOOL["description"],
        "parameters": _TOOL["input_schema"],
    },
}


# ---------------------------------------------------------------------------
# Generation — Anthropic
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
    # Estimate cost (Opus 4.6 pricing)
    input_cost = u.input_tokens / 1e6 * 5
    output_cost = u.output_tokens / 1e6 * 25
    print(f"  Usage: input={u.input_tokens}  output={u.output_tokens}  "
          f"(~${input_cost + output_cost:.4f})")

    for block in response.content:
        if block.type == "tool_use" and block.name == "create_campaign":
            raw = block.input
            # Force-convert to standard Python types (handles SDK wrapper objects)
            if isinstance(raw, str):
                raw = json.loads(raw)
            else:
                raw = json.loads(json.dumps(raw))
            _log_campaign_core_usage(
                provider=provider,
                model=model,
                theme=theme,
                node_count=node_count,
                lang=lang,
                tone_hint=tone_hint,
                worldview_hint=worldview_hint,
                campaign_id=raw["campaign_id"],
                title=raw.get("title", raw["campaign_id"]),
                usage_input=u.input_tokens,
                usage_output=u.output_tokens,
            )
            return raw

    raise RuntimeError(
        f"No create_campaign tool call in response. stop_reason={response.stop_reason}"
    )


# ---------------------------------------------------------------------------
# Generation — OpenAI-compatible (DeepSeek, Qwen, GPT, …)
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
                raw = tc.function.arguments
                if isinstance(raw, str):
                    raw = json.loads(raw)
                usage_input = usage.prompt_tokens if usage else 0
                usage_output = usage.completion_tokens if usage else 0
                _log_campaign_core_usage(
                    provider=provider,
                    model=model,
                    theme=theme,
                    node_count=node_count,
                    lang=lang,
                    tone_hint=tone_hint,
                    worldview_hint=worldview_hint,
                    campaign_id=raw["campaign_id"],
                    title=raw.get("title", raw["campaign_id"]),
                    usage_input=usage_input,
                    usage_output=usage_output,
                )
                return raw

    raise RuntimeError(
        f"No create_campaign tool call in response. "
        f"finish_reason={response.choices[0].finish_reason}"
    )


# ---------------------------------------------------------------------------
# Generation — dispatcher
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
            theme,
            node_count,
            lang,
            provider,
            model,
            api_key,
            tone_hint=tone_hint,
            worldview_hint=worldview_hint,
        )
    return await _generate_openai_compat(
        theme,
        node_count,
        lang,
        provider,
        model,
        base_url or "",
        api_key,
        tone_hint=tone_hint,
        worldview_hint=worldview_hint,
    )


def _build_user_msg(
    theme: str,
    node_count: int,
    lang: str,
    tone_hint: str | None = None,
    worldview_hint: str | None = None,
) -> str:
    """Build the generation request shared by all providers."""

    parts = [
        f"Design a Loombound campaign with approximately {node_count} nodes.",
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
        "Make sure every node_id in next_nodes actually exists in your nodes list."
    )
    if lang == "zh":
        parts.append(
            "Write all narrative text (title, intro, tone, label, map_blurb) in Chinese (中文). "
            "node_id and node_type remain in English snake_case."
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Response normalisation
# ---------------------------------------------------------------------------

def _normalise(data: dict) -> dict:
    """Normalise model response: accept nodes as list OR dict.

    Some models return "nodes" as {node_id: spec} instead of the required array.
    Non-dict list items (bare strings, etc.) are dropped so validate_graph can
    report a clean error instead of crashing with a TypeError.
    """
    nodes = data.get("nodes", [])
    data = dict(data)
    if isinstance(nodes, dict):
        normalised: list[dict] = []
        for node_id, spec in nodes.items():
            if isinstance(spec, dict):
                spec = dict(spec)
                spec.setdefault("node_id", node_id)
                normalised.append(spec)
        data["nodes"] = normalised
    elif isinstance(nodes, list):
        # Drop any items that are not dicts (e.g. bare node_id strings)
        data["nodes"] = [n for n in nodes if isinstance(n, dict)]
    return data


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_graph(nodes: list[dict], start_node_id: str) -> list[str]:
    errors: list[str] = []
    if not nodes:
        errors.append("nodes list is empty — model returned no nodes or wrong format")
        return errors
    bad = [i for i, n in enumerate(nodes) if not isinstance(n, dict)]
    if bad:
        errors.append(f"nodes[{bad}] are not objects — malformed response from model")
        return errors
    node_ids = {n["node_id"] for n in nodes}

    if start_node_id not in node_ids:
        errors.append(f"start_node_id '{start_node_id}' not found in nodes")

    for node in nodes:
        for ref in node.get("next_nodes", []):
            if ref not in node_ids:
                errors.append(
                    f"'{node['node_id']}' → '{ref}': referenced node does not exist"
                )

    if not any(not n.get("next_nodes") for n in nodes):
        errors.append("No terminal nodes (next_nodes: []) — campaign has no ending")

    return errors


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_campaign(data: dict, out_name: str) -> tuple[Path, int]:
    campaign_id = data["campaign_id"]
    nodes_raw: list[dict] = data["nodes"]

    campaigns_dir = REPO_ROOT / "data" / "campaigns"
    nodes_dir = REPO_ROOT / "data" / "nodes" / campaign_id
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    nodes_dir.mkdir(parents=True, exist_ok=True)

    campaign_nodes: dict = {}
    for node in nodes_raw:
        nid = node["node_id"]
        node_file_rel = f"data/nodes/{campaign_id}/{nid}.json"
        node_file_abs = REPO_ROOT / node_file_rel

        # Write node spec file (arbitrations is an integer → LLM-generated at runtime)
        node_spec = {
            "node_id": f"{nid}:floor_{node['floor']:02d}",
            "node_type": node["node_type"],
            "floor": node["floor"],
            "metadata": {"scene_summary": node["map_blurb"]},
            "arbitrations": node["arbitration_count"],
        }
        node_file_abs.write_text(
            json.dumps(node_spec, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        campaign_nodes[nid] = {
            "label":      node["label"],
            "map_blurb":  node["map_blurb"],
            "node_file":  node_file_rel,
            "next_nodes": node["next_nodes"],
        }

    campaign_json = {
        "campaign_id":        campaign_id,
        "title":              data["title"],
        "intro":              data["intro"],
        "tone":               data.get("tone", ""),
        "initial_core_state": data["initial_core_state"],
        "initial_meta_state": {
            "active_conditions": [],
            "metadata": {"major_events": [], "traumas": []},
        },
        "start_node_id": data["start_node_id"],
        "nodes":         campaign_nodes,
    }

    out_path = campaigns_dir / f"{out_name}.json"
    out_path.write_text(
        json.dumps(campaign_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path, len(nodes_raw)


# ---------------------------------------------------------------------------
# Graph visualiser
# ---------------------------------------------------------------------------

def print_graph(data: dict) -> None:
    nodes = {n["node_id"]: n for n in data["nodes"]}
    start = data["start_node_id"]
    visited: set[str] = set()

    print("\n  Campaign graph:")

    def _print_node(nid: str, prefix: str, is_last: bool) -> None:
        if nid not in nodes:
            print(f"{prefix}{'└─' if is_last else '├─'} [missing: {nid}]")
            return
        n = nodes[nid]
        connector = "└─" if is_last else "├─"
        tag = " ←START" if nid == start else ""
        arbs = n["arbitration_count"]
        print(f"{prefix}{connector} [{n['node_type']}] {nid}  (arb×{arbs}){tag}")
        if nid in visited:
            child_prefix = prefix + ("   " if is_last else "│  ")
            print(f"{child_prefix}  (already shown above)")
            return
        visited.add(nid)
        children = n.get("next_nodes", [])
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(children):
            _print_node(child, child_prefix, i == len(children) - 1)

    _print_node(start, "  ", True)
    terminal = [n["node_id"] for n in data["nodes"] if not n.get("next_nodes")]
    print(f"\n  Terminal node(s): {terminal}")
    total_arbs = sum(n["arbitration_count"] for n in data["nodes"])
    print(f"  Total arbitrations (LLM-generated at runtime): {total_arbs}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate a Loombound campaign."
    )
    parser.add_argument(
        "theme",
        nargs="?",
        default="drowned city cult investigation",
        help="Campaign theme (default: 'drowned city cult investigation')",
    )
    parser.add_argument("--nodes", type=int, default=6, metavar="N",
                        help="Approximate number of nodes (default: 6)")
    parser.add_argument("--out", default=None, metavar="NAME",
                        help="Output filename stem (default: campaign_id from model)")
    parser.add_argument("--lang", choices=["en", "zh"], default="en",
                        help="Language for narrative text (default: en)")
    parser.add_argument(
        "--tone",
        default=None,
        metavar="TEXT",
        help="Explicit tone guidance for campaign generation "
             "(e.g. 'melancholic solarpunk mystery with hopeful undertones').",
    )
    parser.add_argument(
        "--worldview",
        default=None,
        metavar="TEXT",
        help="Explicit worldview/setting guidance for campaign generation "
             "(e.g. 'post-collapse orbital stations run by debt guilds').",
    )
    parser.add_argument("--retries", type=int, default=3,
                        help="Max attempts on graph validation failure (default: 3)")
    parser.add_argument(
        "--provider",
        default="anthropic",
        metavar="PROVIDER",
        help="AI provider: anthropic (default), deepseek, openai, qwen. "
             "Can also be set via CAMPAIGN_CORE_PROVIDER env var.",
    )
    parser.add_argument(
        "--provider-model",
        dest="provider_model",
        default=None,
        metavar="MODEL",
        help="Override model name for the chosen provider. "
             "Can also be set via CAMPAIGN_CORE_MODEL env var.",
    )
    args = parser.parse_args()

    # Resolve provider and model
    provider = os.environ.get("CAMPAIGN_CORE_PROVIDER", args.provider)
    provider_model_override = (
        args.provider_model or os.environ.get("CAMPAIGN_CORE_MODEL")
    )

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
            f"Error: {api_key_env} not set in .env or environment "
            f"(required for provider '{provider}').",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Generating campaign: '{args.theme}' (~{args.nodes} nodes) via {provider}/{model}")

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

        errors = validate_graph(data["nodes"], data["start_node_id"])
        if errors:
            print(f"\nGraph validation failed (attempt {attempt}):")
            for e in errors:
                print(f"  ✗ {e}")
            if attempt == args.retries:
                print("\nAll retries exhausted.", file=sys.stderr)
                sys.exit(1)
            continue

        # Success
        print_graph(data)

        out_name = args.out or data["campaign_id"]
        out_path, node_count = write_campaign(data, out_name)

        print(f"\n  Written: {out_path}")
        print(f"  Written: data/nodes/{data['campaign_id']}/ ({node_count} node files)")
        print(f"\nTo play:")
        print(f"  ./run.sh --campaign {out_path} --slow deepseek --lang {args.lang}")
        break


if __name__ == "__main__":
    main()
