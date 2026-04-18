#!/usr/bin/env python3
"""Generate a Loombound saga.

Step 1: Claude Opus generates the saga graph (waypoint topology, labels, map_blurbs).
Step 2: Claude Haiku generates T1 cache — scene skeletons for every waypoint (batch, one call).

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

from src.t2.core.gen_a1_cache_table import generate_t1_cache_table_step

REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parents[3]
)
_LLM_LOG = REPO_ROOT / "logs" / "llm.md"



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
You are a saga designer for a text-adventure roguelite. Your sole job is to call \
create_campaign exactly once with a complete, structurally valid saga based on the \
theme the user provides. Invent the tone, setting, and genre yourself — do not default \
to any particular aesthetic unless the theme clearly implies one.

─── SAGA DESIGN RULES ──────────────────────────────────────────────────────
NODE GRAPH
- All waypoint_ids referenced in any waypoint's next_waypoints MUST appear as a waypoint_id in your waypoints list.
- start_waypoint_id MUST be one of the waypoint_ids you define.
- At least one waypoint must have next_waypoints: [] (the terminal node — saga's climax).
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
Write a 2–4 sentence description of the saga's genre, atmosphere, and aesthetic. \
This will be injected into the content generator for every waypoint. Be specific: name the \
genre, the mood, the kind of imagery that should recur. This is the single most \
important field for content coherence.

map_blurb: 1–2 sentences the player sees on the map. Specific and evocative.
intro: 2–3 sentences setting the whole saga's opening mood.

VERDICT DICTIONARY
Generate 3–6 saga-specific toll labels that describe option consequences.
- Always include "stable" (net delta ≥ 0) and "destabilizing" (net delta clearly negative).
- Add 1–4 theme-specific entries that fit your saga's tone (e.g. "cursed", "exploitative", "honorable", "corrupting").
- Each entry needs a one-line description of the numeric constraints it implies for h/m/s values.
- These labels will be used by the runtime AI to classify options before assigning numbers.

RULES
Generate 3–5 saga-specific rules that define the psychological logic of this world. \
Each rule is a pattern the protagonist should follow to maintain stability — a discipline, \
a survival heuristic, a moral code forged by this world's specific pressures.
- id: snake_case, descriptive (e.g. "rule_never_open_unmarked_doors")
- name: a short, memorable maxim phrased as guidance ("When the fog thickens, trust the cold")
- theme: must be one of the snake_case keys you define in narration_table
- decision_types: which scene types trigger this rule (crossroads, market, encounter, archive, ritual, threshold, rest, investigation)
- priority: 60–120 (higher = checked first)
- sanity_penalty: integer 0–3 (cost if the rule is violated)
- preferred_option_tags: tags on options this rule favors
- forbidden_option_tags: tags on options this rule forbids
- match (optional): resource bounds or required_context_tags that restrict when the rule fires \
  (max_health, min_health, max_money, min_money, max_sanity, min_sanity, required_context_tags)
Make the rules feel like they were written by someone who survived this world, not a game designer.

NARRATION TABLE
Define 10–15 psychological theme labels for this saga. Each entry is a snake_case key mapped \
to one sentence shown to the player after a choice — a brief internal state, mood, or sensation \
the protagonist feels at that moment of psychological pressure.
Rules:
- Write in second person ("You…" / "你…"). One sentence per theme, under 20 words.
- Describe inner experience only — no concrete actions, no invented specifics (no page numbers, \
  names, or locations).
- Must include a "neutral" key as the default fallback.
- These keys also serve as the valid values for rule.theme — design them to cover the \
  psychological range your rules will need.

Call create_campaign exactly once.
"""

_TOOL = {
    "name": "create_campaign",
    "description": "Output a complete Loombound saga structure.",
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
                "description": "Starting stats. max_health and sanity are fixed at 100; set health=100, max_health=100, sanity=100. Choose money freely (suggest 5–15). depth=1, act=1.",
                "properties": {
                    "health":     {"type": "integer", "const": 100},
                    "max_health": {"type": "integer", "const": 100},
                    "money":      {"type": "integer"},
                    "sanity":     {"type": "integer", "const": 100},
                    "depth":      {"type": "integer", "const": 1},
                    "act":        {"type": "integer", "const": 1},
                },
                "required": ["health", "max_health", "money", "sanity", "depth", "act"],
                "additionalProperties": False,
            },
            "tone": {
                "type": "string",
                "description": (
                    "2–4 sentences describing the saga's genre, atmosphere, and aesthetic. "
                    "Used by the runtime content generator for every waypoint. Be specific."
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
                            "description": "snake_case, unique within saga",
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
                    "3–6 saga-specific toll labels. "
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
                "description": "3–5 saga-specific rules defining this world's psychological logic.",
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
                    "10–15 per-saga psychological theme labels. "
                    "Each key is a snake_case theme name; each value is one sentence of inner experience. "
                    "Must include 'neutral'. Rule.theme values must be keys from this table."
                ),
                "additionalProperties": {"type": "string"},
                "minProperties": 10,
            },
        },
        "required": ["saga_id", "title", "intro", "tone", "initial_core_state", "start_waypoint_id", "waypoints", "toll_lexicon", "rules", "narration_table"],
        "additionalProperties": False,
    },
}

# ---------------------------------------------------------------------------
# Campaign graph generation — Anthropic (Opus)
# ---------------------------------------------------------------------------

async def _generate_anthropic(
    theme: str,
    node_count: int,
    lang: str,
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
                provider="anthropic", model=model, theme=theme,
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




def _build_user_msg(
    theme: str,
    node_count: int,
    lang: str,
    tone_hint: str | None = None,
    worldview_hint: str | None = None,
) -> str:
    parts = [
        f"Design a Loombound saga with exactly {node_count} waypoints.",
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
        for waypoint_id, spec in nodes.items():
            if isinstance(spec, dict):
                spec = dict(spec)
                spec.setdefault("waypoint_id", waypoint_id)
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
    start_waypoint_id: str,
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

    if start_waypoint_id not in node_ids:
        errors.append(f"start_waypoint_id '{start_waypoint_id}' not found in nodes")

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
        errors.append("No terminal nodes (next_waypoints: []) — saga has no ending")

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
        "initial_core_state": {
            **data["initial_core_state"],
            "health": 100,
            "max_health": 100,
            "sanity": 100,
            "depth": 1,
            "act": 1,
        },
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
    model: str,
    api_key: str,
) -> dict:
    """Generate and validate the saga graph, retrying up to args.retries times.

    Calls sys.exit(1) if all retries fail.
    """
    data: dict | None = None
    for attempt in range(1, args.retries + 1):
        if attempt > 1:
            print(f"\nRetrying (attempt {attempt}/{args.retries})...")
        try:
            data = _normalise(asyncio.run(
                _generate_anthropic(
                    args.theme, args.nodes, args.lang,
                    model, api_key,
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

    parser = argparse.ArgumentParser(description="Generate a Loombound saga.")
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
        help="Skip T1 cache generation (saga graph only).",
    )
    args = parser.parse_args()

    model = os.environ.get("CAMPAIGN_CORE_MODEL") or "claude-opus-4-6"
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    if not args.skip_t1_cache:
        anthropic_key = api_key
    else:
        anthropic_key = None

    print(f"Generating saga: '{args.theme}' ({args.nodes} nodes) via {model}")

    # ── Step 1: generate saga graph ─────────────────────────────────────────

    data = _step1_generate_graph(args, model, api_key)

    print_graph(data)

    out_name = args.out or data["saga_id"]
    generation_context = {
        "theme":          args.theme,
        "language":       args.lang,
        "provider":       "anthropic",
        "model":          model,
        "tone_hint":      args.tone,
        "worldview_hint": args.worldview,
    }
    out_path, node_count = write_campaign(data, out_name, generation_context=generation_context)

    print(f"\n  Written: {out_path} ({node_count} nodes inlined)")

    # ── Step 2: generate T1 cache (Haiku, batched 3 nodes per call) ────────

    if not args.skip_t1_cache and anthropic_key:
        generate_t1_cache_table_step(data, node_count, args.lang, anthropic_key)

    saga_id = data['saga_id']
    print(f"\nSAGA_ID={saga_id}")
    print(f"SAGA_PATH={out_path}")
    print(f"\nTo play:")
    print(f"  ./loombound run --saga {saga_id} --lang {args.lang}")


if __name__ == "__main__":
    main()
