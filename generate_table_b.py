"""Offline script: generate M2 Table B — per-campaign ArbitrationSeed content.

Reads data/m2_table_a.json and a campaign JSON, then calls DeepSeek once per
Table A entry to generate a full ArbitrationSeed (scene_concept, sanity_axis,
options with intent/tags/effects).

Output: data/nodes/<campaign_id>/table_b.json

Usage:
    python generate_table_b.py --campaign data/campaigns/act1_campaign.json
    python generate_table_b.py --campaign data/campaigns/my_campaign.json --max-entries 10

Requires DEEPSEEK_API_KEY in environment or .env file.
DeepSeek is accessed via the OpenAI-compatible API at https://api.deepseek.com/v1
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import openai

REPO_ROOT = Path(__file__).parent
ENV_PATH = REPO_ROOT / ".env"
TABLE_A_PATH = REPO_ROOT / "data" / "m2_table_a.json"
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


def _build_system_prompt(title: str, tone: str, intro: str) -> str:
    context_lines = []
    if title:
        context_lines.append(f"Campaign title: {title}")
    if tone:
        context_lines.append(f"Tone / atmosphere: {tone}")
    if intro:
        context_lines.append(f"Story premise: {intro}")
    context_block = "\n".join(context_lines)
    return f"""\
You are a narrative content designer for a roguelite game.

{context_block}

Your task: given an arc state (entry_id + four categorical fields), generate
a complete ArbitrationSeed — a structured scene plan the game engine uses to
drive one narrative encounter.

The scene must fit the campaign's setting, tone, and premise above.
Output the ArbitrationSeed as a JSON object via the generate_seed tool.
Use tendency language (quasi-precise), not exact numbers.
Options should create meaningful narrative choice under pressure.
Do not produce any output outside the tool call.
"""


_TOOL = {
    "name": "generate_seed",
    "description": "Submit the ArbitrationSeed for the given arc state.",
    "parameters": {
        "type": "object",
        "properties": {
            "entry_id": {
                "type": "integer",
                "description": "Must match the entry_id of the input arc state.",
            },
            "scene_type": {
                "type": "string",
                "description": "Scene category (e.g. encounter, merchant, event, rest, boss).",
            },
            "scene_concept": {
                "type": "string",
                "description": "1-2 sentence quasi description of the scene premise.",
            },
            "sanity_axis": {
                "type": "string",
                "description": "The psychological tension the scene centres on (tendency language).",
            },
            "options": {
                "type": "array",
                "description": "2-4 player choices.",
                "items": {
                    "type": "object",
                    "properties": {
                        "option_id": {"type": "string"},
                        "intent": {
                            "type": "string",
                            "description": "Player's motivation for choosing this (1 short phrase).",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Thematic tags (e.g. ['greed', 'danger']).",
                        },
                        "effects": {
                            "type": "object",
                            "description": "Quasi effects: sanity_delta (tendency string), money_delta (tendency string), flags (list of strings).",
                            "properties": {
                                "sanity_delta": {"type": "string"},
                                "money_delta": {"type": "string"},
                                "flags": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "required": ["option_id", "intent", "tags", "effects"],
                },
            },
        },
        "required": ["entry_id", "scene_type", "scene_concept", "sanity_axis", "options"],
    },
}


def _generate_seed(client: openai.OpenAI, system_prompt: str, arc_entry: dict) -> dict | None:
    user_msg = (
        f"Generate an ArbitrationSeed for this arc state:\n"
        f"{json.dumps(arc_entry, ensure_ascii=False)}\n\n"
        f"Call generate_seed with the result."
    )
    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            tools=[{"type": "function", "function": _TOOL}],
            tool_choice={"type": "function", "function": {"name": "generate_seed"}},
            max_tokens=1024,
        )
        for choice in response.choices:
            msg = choice.message
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.function.name == "generate_seed":
                        raw = tc.function.arguments
                        if isinstance(raw, str):
                            raw = json.loads(raw)
                        return raw
    except Exception as exc:
        print(f"  [error] entry_id={arc_entry.get('entry_id')}: {exc}")
    return None


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Generate per-campaign M2 Table B.")
    parser.add_argument("--campaign", type=Path, required=True, help="Campaign JSON file path.")
    parser.add_argument(
        "--table-a",
        type=Path,
        default=TABLE_A_PATH,
        help="Table A JSON path (default: data/m2_table_a.json).",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N entries (useful for testing).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        metavar="SEC",
        help="Seconds to wait between DeepSeek calls (default: 0.5).",
    )
    args = parser.parse_args()

    # Load Table A
    if not args.table_a.exists():
        raise FileNotFoundError(f"Table A not found at {args.table_a}. Run generate_table_a.py first.")
    with args.table_a.open(encoding="utf-8") as f:
        table_a: list[dict] = json.load(f)

    # Load campaign
    with args.campaign.open(encoding="utf-8") as f:
        campaign = json.load(f)
    campaign_id = campaign.get("campaign_id", args.campaign.stem)
    title = campaign.get("title", "")
    tone = campaign.get("tone", "")
    intro = campaign.get("intro", "")

    # DeepSeek client
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set. Add it to .env or export it before running.")
    client = openai.OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    system_prompt = _build_system_prompt(title=title, tone=tone, intro=intro)

    entries_to_process = table_a[:args.max_entries] if args.max_entries else table_a
    table_b: list[dict] = []
    failed: list[int] = []

    print(f"Generating Table B for campaign '{campaign_id}' ({len(entries_to_process)} entries)...")

    for i, arc_entry in enumerate(entries_to_process, start=1):
        entry_id = arc_entry["entry_id"]
        print(f"  [{i}/{len(entries_to_process)}] entry_id={entry_id} ...", end=" ", flush=True)
        seed = _generate_seed(client, system_prompt, arc_entry)
        if seed is not None:
            # Attach the M2 arc fields alongside the seed
            table_b.append({
                "entry_id": entry_id,
                "m2": arc_entry,
                **seed,
            })
            print("ok")
        else:
            failed.append(entry_id)
            print("FAILED")
        if i < len(entries_to_process) and args.delay > 0:
            time.sleep(args.delay)

    # Save output
    out_dir = REPO_ROOT / "data" / "nodes" / campaign_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "table_b.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(table_b, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(table_b)} entries to {out_path}")
    if failed:
        print(f"Failed entry_ids (can retry): {failed}")


if __name__ == "__main__":
    main()
