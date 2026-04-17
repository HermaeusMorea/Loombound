"""Offline script: generate the T1 cache (per-campaign node scene skeletons).

Called automatically by generate_campaign.py after the campaign graph is built.
Can also be run standalone to regenerate T1 cache for an existing campaign.

Calls Claude Haiku in batches of 3 nodes per call. Produces one entry per node
containing scene_concept, sanity_axis, and option intents — no numeric effect
values. Effect values are assigned at runtime by the M2 arc classifier (Haiku).

Output: data/nodes/<campaign_id>/t1_cache.json

Usage (standalone):
    python gen_t1_cache.py data/campaigns/my_campaign.json
    python gen_t1_cache.py data/campaigns/my_campaign.json --lang zh

Requires ANTHROPIC_API_KEY in environment or .env file.
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
    else Path(__file__).resolve().parent.parent
)
_LLM_LOG = REPO_ROOT / "logs" / "llm.md"

_HAIKU_INPUT_COST  = 0.80 / 1_000_000
_HAIKU_OUTPUT_COST = 4.0  / 1_000_000

_T1_CACHE_BATCH_SIZE = 3


# ---------------------------------------------------------------------------
# Shared utilities
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


def _haiku_cost(inp: int, out: int) -> float:
    return inp * _HAIKU_INPUT_COST + out * _HAIKU_OUTPUT_COST


def _coerce_json(raw: object) -> dict:
    if isinstance(raw, str):
        return json.loads(raw)
    return json.loads(json.dumps(raw))


# ---------------------------------------------------------------------------
# T1 cache tool schema (Claude Haiku — batch, all nodes in one call)
# ---------------------------------------------------------------------------

_SKELETON_ITEM = {
    "type": "object",
    "properties": {
        "scene_type": {"type": "string"},
        "scene_concept": {
            "type": "string",
            "description": "1-2 sentences: what physically happens here. Specific, tendency-flexible.",
        },
        "sanity_axis": {
            "type": "string",
            "description": "One short phrase naming the tension (e.g. 'obedience vs conscience'). No analysis.",
        },
        "options": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "option_id": {"type": "string"},
                    "intent":    {"type": "string"},
                    "tags":      {"type": "array", "items": {"type": "string"}},
                    "effects": {
                        "type": "object",
                        "properties": {
                            "health_delta":    {"type": "integer"},
                            "money_delta":     {"type": "integer"},
                            "sanity_delta":    {"type": "integer"},
                            "add_conditions":  {"type": "array", "items": {"type": "string"}},
                        },
                        "additionalProperties": False,
                    },
                },
                "required": ["option_id", "intent", "tags", "effects"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scene_type", "scene_concept", "sanity_axis", "options"],
    "additionalProperties": False,
}

_T1_CACHE_TOOL = {
    "name": "generate_t1_cache",
    "description": "Submit scene skeletons for ALL campaign nodes at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "arbitrations": {
                            "type": "array",
                            "minItems": 1,
                            "items": _SKELETON_ITEM,
                        },
                    },
                    "required": ["node_id", "arbitrations"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["nodes"],
        "additionalProperties": False,
    },
}

_T1_CACHE_SYSTEM = """\
You are a narrative scene designer for a roguelite game.
Your task: generate stable, tendency-flexible scene skeletons for the nodes listed below.

Rules:
- Call generate_t1_cache exactly once with ALL the nodes given to you in this message.
- Each node must have EXACTLY the number of arbitrations specified.
- scene_concept: what physically happens — specific but not locked to one dramatic outcome.
- sanity_axis: one short phrase naming the psychological tension (e.g. "loyalty vs survival"). Do NOT analyze or explain it — just name it. Runtime Fast Core will develop it into prose.
- Do not hardcode a single dramatic tendency; runtime arc state will modulate these later.
"""


# ---------------------------------------------------------------------------
# Prompt builder + validator
# ---------------------------------------------------------------------------

def _build_t1_cache_user_msg(
    nodes_raw: list[dict],
    title: str,
    tone: str,
    intro: str,
    lang: str,
) -> tuple[str, dict[str, int]]:
    """Build the user message for a T1 cache batch call.

    Returns (user_msg, expected) where expected maps node_id → arbitration count.
    """
    node_lines = []
    expected: dict[str, int] = {}
    for node in nodes_raw:
        nid = node["node_id"]
        arb_n = int(node.get("arbitration_count", 1))
        expected[nid] = arb_n
        node_lines.append(
            f"  - node_id: {nid}  node_type: {node.get('node_type', '')}  "
            f"floor: {node.get('floor', 1)}  arbitrations_required: {arb_n}\n"
            f"    label: {node.get('label', '')}\n"
            f"    map_blurb: {node.get('map_blurb', '')}"
        )

    lang_note = (
        "Write all narrative text (scene_concept, sanity_axis, intent) in Chinese (中文).\n"
        if lang == "zh" else ""
    )
    user_msg = (
        f"Campaign: {title}\n"
        f"Tone: {tone}\n"
        f"Premise: {intro}\n\n"
        f"{lang_note}"
        f"Generate T1 cache skeletons for ALL {len(nodes_raw)} nodes listed below.\n"
        f"Each node must have EXACTLY the specified number of arbitrations.\n\n"
        + "\n".join(node_lines)
    )
    return user_msg, expected


def _validate_t1_cache_response(raw: dict, expected: dict[str, int]) -> list[str]:
    """Return a list of validation error strings (empty = valid).

    Checks both structure (node presence, arbitration count) and content
    (non-empty scene_concept, sanity_axis, and option intents/ids).
    """
    result_nodes = raw.get("nodes", [])
    result_by_id = {n["node_id"]: n for n in result_nodes if isinstance(n, dict)}
    errors: list[str] = []
    for nid, want in expected.items():
        got_node = result_by_id.get(nid)
        if got_node is None:
            errors.append(f"missing node_id={nid}")
            continue
        arbs = got_node.get("arbitrations", [])
        got = len(arbs)
        if got != want:
            errors.append(f"{nid}: expected {want} arbitrations, got {got}")
            continue
        for arb_idx, arb in enumerate(arbs):
            prefix = f"{nid}[{arb_idx}]"
            if not str(arb.get("scene_concept", "")).strip():
                errors.append(f"{prefix}: scene_concept is empty")
            if not str(arb.get("sanity_axis", "")).strip():
                errors.append(f"{prefix}: sanity_axis is empty")
            options = arb.get("options", [])
            if not options:
                errors.append(f"{prefix}: options list is empty")
            for opt_idx, opt in enumerate(options):
                if not str(opt.get("option_id", "")).strip():
                    errors.append(f"{prefix} opt[{opt_idx}]: option_id is empty")
                if not str(opt.get("intent", "")).strip():
                    errors.append(f"{prefix} opt[{opt_idx}]: intent is empty")
    return errors


# ---------------------------------------------------------------------------
# Haiku API call
# ---------------------------------------------------------------------------

async def _generate_t1_cache(
    nodes_raw: list[dict],
    campaign_id: str,
    tone: str,
    title: str,
    intro: str,
    lang: str,
    api_key: str,
    *,
    max_retries: int = 2,
) -> list[dict] | None:
    """Call Claude Haiku to generate T1 cache for all nodes in one batch."""

    client = anthropic.AsyncAnthropic(api_key=api_key)
    model = "claude-haiku-4-5-20251001"

    user_msg, expected = _build_t1_cache_user_msg(nodes_raw, title, tone, intro, lang)

    _md_log([
        f"## [{_ts()}] T1 CACHE REQUEST — `{campaign_id}` ({len(nodes_raw)} nodes)",
        f"model: {model}",
        *[f"  {n['node_id']} arb×{n.get('arbitration_count', 1)}" for n in nodes_raw],
    ])

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=8000,
                system=_T1_CACHE_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
                tools=[_T1_CACHE_TOOL],
                tool_choice={"type": "tool", "name": "generate_t1_cache"},
            )
        except Exception as exc:
            print(f"  [T1 cache attempt {attempt}] API error: {exc}")
            if attempt == max_retries:
                return None
            continue

        u = response.usage
        raw: dict | None = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "generate_t1_cache":
                raw = _coerce_json(block.input)
                break

        if raw is None:
            print(f"  [T1 cache attempt {attempt}] no tool call returned, retrying...")
            continue

        errors = _validate_t1_cache_response(raw, expected)
        result_nodes = raw.get("nodes", [])

        if errors:
            print(f"  [T1 cache attempt {attempt}] validation errors: {errors}")
            _md_log([
                f"## [{_ts()}] T1 CACHE RETRY — `{campaign_id}` attempt={attempt}",
                *errors,
            ])
            if attempt == max_retries:
                return None
            continue

        # Stamp node metadata client-side (keeps T1 cache self-contained)
        node_meta = {n["node_id"]: n for n in nodes_raw}
        t1_cache: list[dict] = []
        for n in result_nodes:
            nid = n["node_id"]
            meta = node_meta.get(nid, {})
            t1_cache.append({
                "node_id":    nid,
                "node_type":  meta.get("node_type", ""),
                "label":      meta.get("label", ""),
                "map_blurb":  meta.get("map_blurb", ""),
                "arbitrations": n["arbitrations"],
            })

        haiku_cost = _haiku_cost(u.input_tokens, u.output_tokens)
        print(f"  T1 cache: input={u.input_tokens}  output={u.output_tokens}  "
              f"(~${haiku_cost:.4f})")
        _md_log([
            f"## [{_ts()}] T1 CACHE RESPONSE — `{campaign_id}` attempt={attempt}",
            f"model: {model}",
            f"tokens — input: {u.input_tokens}  output: {u.output_tokens}",
            f"cost: ${haiku_cost:.4f}",
            "summaries:",
            *[
                f"  {row['node_id']} (arb×{len(row['arbitrations'])}): "
                + (row['arbitrations'][0].get('scene_concept', '')[:90] if row.get('arbitrations') else '(empty)')
                for row in t1_cache
            ],
        ])
        return t1_cache

    return None


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------

def write_t1_cache(t1_cache: list[dict], campaign_id: str) -> Path:
    out_dir = REPO_ROOT / "data" / "nodes" / campaign_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "t1_cache.json"
    out_path.write_text(json.dumps(t1_cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Public step function (called by generate_campaign.py)
# ---------------------------------------------------------------------------

def generate_t1_cache_step(
    data: dict,
    node_count: int,
    lang: str,
    anthropic_key: str,
) -> None:
    """Generate T1 cache skeletons for all nodes (batched) and write to disk."""
    nodes_list = data["nodes"]
    batch_size = _T1_CACHE_BATCH_SIZE
    batches = [nodes_list[i:i + batch_size] for i in range(0, len(nodes_list), batch_size)]
    print(f"\nGenerating T1 cache via claude-haiku ({node_count} nodes, {len(batches)} batch(es) of ≤{batch_size})...")

    async def _run_batches() -> tuple[list[dict], bool]:
        results: list[dict] = []
        failed = False
        for b_idx, batch in enumerate(batches, start=1):
            batch_ids = [n["node_id"] for n in batch]
            print(f"  Batch {b_idx}/{len(batches)}: {batch_ids}")
            result = await _generate_t1_cache(
                nodes_raw=batch,
                campaign_id=data["campaign_id"],
                tone=data.get("tone", ""),
                title=data.get("title", ""),
                intro=data.get("intro", ""),
                lang=lang,
                api_key=anthropic_key,
            )
            if result:
                results.extend(result)
            else:
                failed = True
                print(f"  Batch {b_idx} failed.", file=sys.stderr)
        return results, failed

    t1_cache_all, any_failed = asyncio.run(_run_batches())

    if t1_cache_all:
        t1_path = write_t1_cache(t1_cache_all, data["campaign_id"])
        print(f"  Written: {t1_path} ({len(t1_cache_all)} nodes)")
    if any_failed:
        print("  Some batches failed — re-run gen to regenerate T1 cache.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Generate T1 cache for an existing campaign.")
    parser.add_argument("campaign", type=Path, help="Path to campaign JSON file.")
    parser.add_argument("--lang", choices=["en", "zh"], default="en",
                        help="Language for narrative text (default: en)")
    args = parser.parse_args()

    if not args.campaign.exists():
        print(f"Error: campaign file not found: {args.campaign}", file=sys.stderr)
        sys.exit(1)

    campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
    nodes_list = list(campaign.get("nodes", {}).values()) if isinstance(campaign["nodes"], dict) \
        else campaign.get("nodes", [])

    for node in nodes_list:
        if "arbitration_count" not in node:
            node["arbitration_count"] = node.get("arbitrations", 1) if isinstance(
                node.get("arbitrations"), int) else 1

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    data = {
        "campaign_id": campaign["campaign_id"],
        "title":       campaign.get("title", ""),
        "tone":        campaign.get("tone", ""),
        "intro":       campaign.get("intro", ""),
        "nodes":       nodes_list,
    }
    generate_t1_cache_step(data, len(nodes_list), args.lang, api_key)


if __name__ == "__main__":
    main()
