"""Offline script: generate per-node Table B scene skeletons for one campaign.

Unlike the old design, Table B is no longer keyed by every Table A entry_id.
Instead, each row is keyed by campaign node_id and stores one or more scene
skeleta (one per arbitration slot). Runtime Claude still classifies against the
full Table A, and Fast Core then mixes that tendency into these node skeleta.

Output: data/nodes/<campaign_id>/table_b.json

Usage:
    python generate_table_b.py --campaign data/campaigns/act1_campaign.json
    python generate_table_b.py --campaign data/campaigns/my_campaign.json --max-nodes 3
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openai

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
_LLM_LOG = REPO_ROOT / "logs" / "llm.md"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"


def _load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    with ENV_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _md_log(lines: list[str]) -> None:
    _LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LLM_LOG.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n\n")


def _generation_context(campaign: dict) -> dict:
    raw = campaign.get("generation_context", {})
    if not isinstance(raw, dict):
        return {}
    return {
        "theme": raw.get("theme", ""),
        "tone_hint": raw.get("tone_hint", ""),
        "worldview_hint": raw.get("worldview_hint", ""),
        "generation_mode": raw.get("generation_mode", "dynamic") or "dynamic",
    }


def _build_system_prompt(
    title: str,
    tone: str,
    intro: str,
    *,
    source_theme: str = "",
    tone_hint: str = "",
    worldview_hint: str = "",
    generation_mode: str = "dynamic",
) -> str:
    context_lines = []
    if source_theme:
        context_lines.append(f"Original user theme: {source_theme}")
    if tone_hint:
        context_lines.append(f"Original tone guidance: {tone_hint}")
    if worldview_hint:
        context_lines.append(f"Original worldview guidance: {worldview_hint}")
    if title:
        context_lines.append(f"Campaign title: {title}")
    if tone:
        context_lines.append(f"Campaign tone / atmosphere: {tone}")
    if intro:
        context_lines.append(f"Campaign premise: {intro}")
    context_lines.append(f"Campaign generation mode: {generation_mode}")
    context_block = "\n".join(context_lines)
    return f"""\
You are a narrative content designer for a roguelite game.

{context_block}

Your task: given one campaign node, generate stable scene skeletons for that node.

Important design rule:
- You are defining what the node physically contains: place, entities, ritual logic,
  commerce, clues, hazards, and likely option shapes.
- You are NOT deciding the final runtime arc tendency. Runtime Claude will later pick
  a Table A arc state, and Fast Core will mix that tendency into the skeleton you create.
- Therefore, make each skeleton structurally vivid but tendency-flexible.

If original user guidance is provided above, treat it as the most authoritative source
for worldview, recurring motifs, factions, technology or magic assumptions, and voice.

Output exactly one tool call.
"""


def _make_tool(arbitration_count: int) -> dict:
    """Build the tool schema with exact minItems/maxItems for arbitration_count."""
    return {
        "name": "generate_node_skeleton",
        "description": (
            f"Submit exactly {arbitration_count} arbitration skeleton(s) for the requested node. "
            f"The 'arbitrations' array MUST contain exactly {arbitration_count} item(s) — no more, no less."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "arbitrations": {
                    "type": "array",
                    "minItems": arbitration_count,
                    "maxItems": arbitration_count,
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene_type": {"type": "string"},
                            "scene_concept": {
                                "type": "string",
                                "description": "1-2 sentences describing the concrete scene skeleton.",
                            },
                            "sanity_axis": {
                                "type": "string",
                                "description": "Base psychological tension; runtime tendency may intensify it later.",
                            },
                            "options": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "option_id": {"type": "string"},
                                        "intent": {"type": "string"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "effects": {
                                            "type": "object",
                                            "properties": {
                                                "health_delta": {"type": "integer"},
                                                "money_delta": {"type": "integer"},
                                                "sanity_delta": {"type": "integer"},
                                                "add_conditions": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["option_id", "intent", "tags", "effects"],
                                },
                            },
                        },
                        "required": ["scene_type", "scene_concept", "sanity_axis", "options"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["arbitrations"],
            "additionalProperties": False,
        },
    }


def _load_node_spec(campaign_node: dict[str, Any]) -> dict[str, Any]:
    raw_path = campaign_node.get("node_file", "")
    if not raw_path:
        raise ValueError("campaign node missing node_file")
    path = Path(raw_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _build_user_message(node_id: str, campaign_node: dict[str, Any], node_spec: dict[str, Any]) -> str:
    arbitration_count = int(node_spec.get("arbitrations", 1) or 1)
    node_type = campaign_node.get("node_type", node_spec.get("node_type", ""))
    label = campaign_node.get("label", "")
    map_blurb = campaign_node.get("map_blurb", "")
    floor_num = node_spec.get("floor", 1)
    return (
        f"You are generating skeletons for ONE node only: '{node_id}'.\n"
        f"Do NOT generate content for any other node.\n\n"
        f"Node details:\n"
        f"  node_id: {node_id}\n"
        f"  node_type: {node_type}\n"
        f"  label: {label}\n"
        f"  map_blurb: {map_blurb}\n"
        f"  floor: {floor_num}\n\n"
        f"Required: fill the 'arbitrations' array with EXACTLY {arbitration_count} item(s).\n"
        f"Keep scene facts specific but tendency-flexible."
    )


_MAX_RETRIES = 3


def _generate_node_skeleton(
    client: openai.OpenAI,
    system_prompt: str,
    *,
    node_id: str,
    campaign_node: dict[str, Any],
    node_spec: dict[str, Any],
) -> dict[str, Any] | None:
    expected_count = int(node_spec.get("arbitrations", 1) or 1)
    user_message = _build_user_message(node_id, campaign_node, node_spec)
    tool = _make_tool(expected_count)

    _md_log([
        f"## [{_ts()}] TABLE B NODE REQUEST — `{node_id}`",
        f"node_type: {campaign_node.get('node_type', node_spec.get('node_type', ''))}",
        f"label: {campaign_node.get('label', '')}",
        f"expected_arbitrations: {expected_count}",
    ])

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                tools=[{"type": "function", "function": tool}],
                tool_choice={"type": "function", "function": {"name": "generate_node_skeleton"}},
                max_tokens=2048,
            )
            usage = response.usage
            raw: dict[str, Any] | None = None
            for choice in response.choices:
                msg = choice.message
                if not msg.tool_calls:
                    continue
                for tc in msg.tool_calls:
                    if tc.function.name == "generate_node_skeleton":
                        parsed = tc.function.arguments
                        if isinstance(parsed, str):
                            parsed = json.loads(parsed)
                        raw = parsed
                        break
                if raw is not None:
                    break

            if raw is None:
                print(f"  [attempt {attempt}] no tool call returned, retrying...")
                continue

            got_count = len(raw.get("arbitrations", []))
            if got_count != expected_count:
                print(
                    f"  [attempt {attempt}] wrong arbitration count: got {got_count}, "
                    f"expected {expected_count} — retrying..."
                )
                _md_log([
                    f"## [{_ts()}] TABLE B NODE RETRY — `{node_id}` attempt={attempt}",
                    f"got_arbitrations: {got_count}  expected: {expected_count}",
                ])
                continue

            # Success — stamp client-side fields so Table B is self-contained
            raw["node_id"] = node_id
            raw["node_type"] = campaign_node.get("node_type", node_spec.get("node_type", ""))
            raw["label"] = campaign_node.get("label", "")
            raw["map_blurb"] = campaign_node.get("map_blurb", "")

            _md_log([
                f"## [{_ts()}] TABLE B NODE RESPONSE — `{node_id}`",
                (
                    f"tokens — input: {usage.prompt_tokens if usage else 0}  "
                    f"output: {usage.completion_tokens if usage else 0}"
                ),
                f"arbitrations: {got_count}  attempt: {attempt}",
                *[
                    (
                        f"  - [{idx}] scene_type={arb.get('scene_type', '')} "
                        f"options={[opt.get('option_id') for opt in arb.get('options', [])]}"
                    )
                    for idx, arb in enumerate(raw.get("arbitrations", []))
                    if isinstance(arb, dict)
                ],
            ])
            return raw

        except Exception as exc:
            _md_log([
                f"## [{_ts()}] TABLE B NODE ERROR — `{node_id}` attempt={attempt}",
                f"error: {exc}",
            ])
            print(f"  [attempt {attempt}] error: {exc}")
            if attempt == _MAX_RETRIES:
                break

    _md_log([f"## [{_ts()}] TABLE B NODE FAILED — `{node_id}`", f"all {_MAX_RETRIES} attempts exhausted"])
    return None


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Generate per-campaign node skeleton Table B.")
    parser.add_argument("--campaign", type=Path, required=True, help="Campaign JSON file path.")
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N nodes (useful for testing).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        metavar="SEC",
        help="Seconds to wait between DeepSeek calls (default: 0.25).",
    )
    args = parser.parse_args()

    with args.campaign.open(encoding="utf-8") as f:
        campaign = json.load(f)

    campaign_id = campaign.get("campaign_id", args.campaign.stem)
    title = campaign.get("title", "")
    tone = campaign.get("tone", "")
    intro = campaign.get("intro", "")
    gen_ctx = _generation_context(campaign)

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set. Add it to .env or export it before running.")
    client = openai.OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    system_prompt = _build_system_prompt(
        title=title,
        tone=tone,
        intro=intro,
        source_theme=gen_ctx["theme"],
        tone_hint=gen_ctx["tone_hint"],
        worldview_hint=gen_ctx["worldview_hint"],
        generation_mode=gen_ctx["generation_mode"],
    )

    node_items = list(campaign.get("nodes", {}).items())
    if args.max_nodes:
        node_items = node_items[:args.max_nodes]

    table_b: list[dict[str, Any]] = []
    failed: list[str] = []

    print(f"Generating Table B node skeletons for campaign '{campaign_id}' ({len(node_items)} nodes)...")

    for i, (node_id, campaign_node) in enumerate(node_items, start=1):
        node_spec = _load_node_spec(campaign_node)
        print(f"  [{i}/{len(node_items)}] node_id={node_id} (arbitrations={int(node_spec.get('arbitrations', 1))}) ...", end=" ", flush=True)
        skeleton = _generate_node_skeleton(
            client,
            system_prompt,
            node_id=node_id,
            campaign_node=campaign_node,
            node_spec=node_spec,
        )
        if skeleton is not None:
            table_b.append(skeleton)
            print("ok")
        else:
            failed.append(node_id)
            print("FAILED")
        if i < len(node_items) and args.delay > 0:
            time.sleep(args.delay)

    out_dir = REPO_ROOT / "data" / "nodes" / campaign_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "table_b.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(table_b, f, indent=2, ensure_ascii=False)

    _md_log([
        f"## [{_ts()}] TABLE B BUILD COMPLETE — `{campaign_id}`",
        f"nodes: {len(table_b)}",
        f"path: {out_path}",
        f"failed_nodes: {failed if failed else '(none)'}",
    ])

    print(f"\nSaved {len(table_b)} node skeleton entries to {out_path}")
    if failed:
        print(f"Failed node_ids (can retry): {failed}")


if __name__ == "__main__":
    main()
