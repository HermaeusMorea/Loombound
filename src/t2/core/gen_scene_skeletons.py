"""Offline script: generate the T1 cache (per-saga waypoint scene skeletons).

Called automatically by generate_saga.py after the saga graph is built.
Can also be run standalone to regenerate T1 cache for an existing saga.

Calls Claude Haiku in batches of 3 nodes per call. Produces one entry per node
containing scene_concept, sanity_axis, and option intents — no numeric effect
values. Effect values are assigned at runtime by the M2 arc classifier (Haiku).

Output: data/waypoints/<saga_id>/scene_skeletons.json

Usage (standalone):
    python -m src.t2.core.gen_scene_skeletons data/sagas/my_saga.json
    python -m src.t2.core.gen_scene_skeletons data/sagas/my_saga.json --lang zh

Requires ANTHROPIC_API_KEY in environment or .env file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import anthropic

from src.shared import config
from src.shared.dotenv import load_dotenv
from src.shared.llm_utils import (
    ts as _ts,
    md_log as _md_log,
    haiku_cost as _haiku_cost,
    extract_tool_input as _extract_tool_input,
    REPO_ROOT,
)

_T1_CACHE_BATCH_SIZE = config.T1_CACHE_BATCH_SIZE


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
                            "add_marks":  {"type": "array", "items": {"type": "string"}},
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
    "name": "generate_scene_skeletons",
    "description": "Submit scene skeletons for ALL saga waypoints at once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "waypoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "waypoint_id": {"type": "string"},
                        "encounters": {
                            "type": "array",
                            "minItems": 1,
                            "items": _SKELETON_ITEM,
                        },
                    },
                    "required": ["waypoint_id", "encounters"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["waypoints"],
        "additionalProperties": False,
    },
}

_T1_CACHE_SYSTEM = """\
You are a narrative scene designer for a roguelite game.
Your task: generate stable, tendency-flexible scene skeletons for the nodes listed below.

Rules:
- Call generate_scene_skeletons exactly once with ALL the nodes given to you in this message.
- Each node must have EXACTLY the number of encounters specified.
- scene_concept: what physically happens — specific but not locked to one dramatic outcome.
- sanity_axis: one short phrase naming the psychological tension (e.g. "loyalty vs survival"). Do NOT analyze or explain it — just name it. Runtime Fast Core will develop it into prose.
- Do not hardcode a single dramatic tendency; runtime arc state will modulate these later.
"""


# ---------------------------------------------------------------------------
# Prompt builder + validator
# ---------------------------------------------------------------------------

def _build_scene_skeletons_user_msg(
    nodes_raw: list[dict],
    title: str,
    tone: str,
    intro: str,
    lang: str,
) -> tuple[str, dict[str, int]]:
    """Build the user message for a T1 cache batch call.

    Returns (user_msg, expected) where expected maps waypoint_id → encounter count.
    """
    node_lines = []
    expected: dict[str, int] = {}
    for node in nodes_raw:
        nid = node["waypoint_id"]
        arb_n = int(node.get("encounter_count", 1))
        expected[nid] = arb_n
        node_lines.append(
            f"  - waypoint_id: {nid}  waypoint_type: {node.get('waypoint_type', '')}  "
            f"depth: {node.get('depth', 1)}  encounters_required: {arb_n}\n"
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
        f"Each node must have EXACTLY the specified number of encounters.\n\n"
        + "\n".join(node_lines)
    )
    return user_msg, expected


def _validate_scene_skeletons_response(raw: dict, expected: dict[str, int]) -> list[str]:
    """Return a list of validation error strings (empty = valid).

    Checks both structure (node presence, encounter count) and content
    (non-empty scene_concept, sanity_axis, and option intents/ids).
    """
    result_nodes = raw.get("waypoints", [])
    result_by_id = {n["waypoint_id"]: n for n in result_nodes if isinstance(n, dict)}
    errors: list[str] = []
    for nid, want in expected.items():
        got_node = result_by_id.get(nid)
        if got_node is None:
            errors.append(f"missing waypoint_id={nid}")
            continue
        arbs = got_node.get("encounters", [])
        got = len(arbs)
        if got != want:
            errors.append(f"{nid}: expected {want} encounters, got {got}")
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

async def _generate_scene_skeletons(
    nodes_raw: list[dict],
    saga_id: str,
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

    _md_log([
        f"## [{_ts()}] A1 CACHE REQUEST — `{saga_id}` ({len(nodes_raw)} waypoints)",
        f"model: {model}",
        *[f"  {n['waypoint_id']} arb×{n.get('encounter_count', 1)}" for n in nodes_raw],
    ])

    accumulated: list[dict] = []
    remaining_nodes = list(nodes_raw)

    for attempt in range(1, max_retries + 1):
        retry_msg, expected = _build_scene_skeletons_user_msg(remaining_nodes, title, tone, intro, lang)
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=16000,
                system=_T1_CACHE_SYSTEM,
                messages=[{"role": "user", "content": retry_msg}],
                tools=[_T1_CACHE_TOOL],
                tool_choice={"type": "tool", "name": "generate_scene_skeletons"},
            )
        except Exception as exc:
            print(f"  [T1 cache attempt {attempt}] API error: {exc}")
            if attempt == max_retries:
                return accumulated or None
            continue

        u = response.usage
        try:
            raw = _extract_tool_input(response, "generate_scene_skeletons")
        except RuntimeError:
            print(f"  [T1 cache attempt {attempt}] no tool call returned, retrying...")
            continue

        errors = _validate_scene_skeletons_response(raw, expected)
        result_nodes = raw.get("waypoints", [])

        if errors:
            # Collect any waypoints that did come back, retry only the missing ones.
            got_ids = {n["waypoint_id"] for n in result_nodes if isinstance(n, dict)}
            accumulated.extend(n for n in result_nodes if isinstance(n, dict))
            remaining_nodes = [n for n in remaining_nodes if n["waypoint_id"] not in got_ids]
            print(f"  [T1 cache attempt {attempt}] validation errors: {errors}")
            _md_log([
                f"## [{_ts()}] A1 CACHE RETRY — `{saga_id}` attempt={attempt}",
                *errors,
            ])
            if attempt == max_retries:
                return accumulated or None
            continue

        # Stamp node metadata client-side (keeps T1 cache self-contained)
        node_meta = {n["waypoint_id"]: n for n in nodes_raw}
        scene_skeletons: list[dict] = []
        for n in accumulated + result_nodes:
            nid = n["waypoint_id"]
            meta = node_meta.get(nid, {})
            scene_skeletons.append({
                "waypoint_id":    nid,
                "waypoint_type":  meta.get("waypoint_type", ""),
                "label":      meta.get("label", ""),
                "map_blurb":  meta.get("map_blurb", ""),
                "encounters": n["encounters"],
            })

        haiku_cost = _haiku_cost(u.input_tokens, u.output_tokens)
        print(f"  T1 cache: input={u.input_tokens}  output={u.output_tokens}  "
              f"(~${haiku_cost:.4f})")
        _md_log([
            f"## [{_ts()}] A1 CACHE RESPONSE — `{saga_id}` attempt={attempt}",
            f"model: {model}",
            f"tokens — input: {u.input_tokens}  output: {u.output_tokens}",
            f"cost: ${haiku_cost:.4f}",
            "summaries:",
            *[
                f"  {row['waypoint_id']} (arb×{len(row['encounters'])}): "
                + (row['encounters'][0].get('scene_concept', '')[:90] if row.get('encounters') else '(empty)')
                for row in scene_skeletons
            ],
        ])
        return scene_skeletons

    return None


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------

def write_scene_skeletons(scene_skeletons: list[dict], saga_id: str) -> Path:
    out_dir = REPO_ROOT / "data" / "waypoints" / saga_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "scene_skeletons.json"
    out_path.write_text(json.dumps(scene_skeletons, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Public step function (called by generate_saga.py)
# ---------------------------------------------------------------------------

def generate_scene_skeletons_step(
    data: dict,
    node_count: int,
    lang: str,
    anthropic_key: str,
) -> None:
    """Generate T1 cache skeletons for all nodes (batched) and write to disk."""
    nodes_list = data["waypoints"]
    batch_size = _T1_CACHE_BATCH_SIZE
    batches = [nodes_list[i:i + batch_size] for i in range(0, len(nodes_list), batch_size)]
    print(f"\nGenerating T1 cache via claude-haiku ({node_count} nodes, {len(batches)} batch(es) of ≤{batch_size})...")

    async def _run_batches() -> tuple[list[dict], bool]:
        results: list[dict] = []
        failed = False
        for b_idx, batch in enumerate(batches, start=1):
            batch_ids = [n["waypoint_id"] for n in batch]
            print(f"  Batch {b_idx}/{len(batches)}: {batch_ids}")
            result = await _generate_scene_skeletons(
                nodes_raw=batch,
                saga_id=data["saga_id"],
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

    scene_skeletons_all, any_failed = asyncio.run(_run_batches())

    if scene_skeletons_all:
        t1_path = write_scene_skeletons(scene_skeletons_all, data["saga_id"])
        print(f"  Written: {t1_path} ({len(scene_skeletons_all)} nodes)")
    if any_failed:
        print("  Some batches failed — re-run gen to regenerate T1 cache.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate T1 cache for an existing saga.")
    parser.add_argument("saga", type=Path, help="Path to saga JSON file.")
    parser.add_argument("--lang", choices=["en", "zh"], default="en",
                        help="Language for narrative text (default: en)")
    args = parser.parse_args()

    if not args.saga.exists():
        print(f"Error: saga file not found: {args.saga}", file=sys.stderr)
        sys.exit(1)

    saga = json.loads(args.saga.read_text(encoding="utf-8"))
    nodes_list = list(saga.get("waypoints", {}).values()) if isinstance(saga["waypoints"], dict) \
        else saga.get("nodes", [])

    for node in nodes_list:
        if "encounter_count" not in node:
            node["encounter_count"] = node.get("encounters", 1) if isinstance(
                node.get("encounters"), int) else 1

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    data = {
        "saga_id": saga["saga_id"],
        "title":       saga.get("title", ""),
        "tone":        saga.get("tone", ""),
        "intro":       saga.get("intro", ""),
        "waypoints":       nodes_list,
    }
    generate_scene_skeletons_step(data, len(nodes_list), args.lang, api_key)


if __name__ == "__main__":
    main()
