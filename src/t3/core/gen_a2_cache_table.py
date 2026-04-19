"""Offline script: generate the T2 cache (global arc-state palette).

One-time setup. Calls Claude Opus once to produce ~50 entries covering the full
space of dramatic arc combinations. The result is loaded into Claude's prompt
cache at runtime so the M2 arc classifier (Haiku) can pick from it cheaply.

Output: data/a2_cache_table.json

Usage:
    python -m src.t3.core.gen_a2_cache_table
    python -m src.t3.core.gen_a2_cache_table --count 50 --output data/t2_cache_table.json

Requires ANTHROPIC_API_KEY in environment or .env file.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import anthropic

from src.shared.dotenv import load_dotenv
from src.shared.llm_utils import (
    ts as _ts,
    md_log as _md_log,
    opus_cost as _opus_cost,
    REPO_ROOT,
)

OUTPUT_PATH = REPO_ROOT / "data" / "a2_cache_table.json"


_SYSTEM_PROMPT = """\
You are a narrative game arc-state designer.

Your task: generate a comprehensive catalogue of arc states for a roguelite narrative game.
Each arc state is a combination of four categorical dimensions that describes
the current dramatic situation of a run.

Dimensions and their values:
  arc_trajectory:    rising | plateau | climax | resolution | pivot
  world_pressure:    low | moderate | high | critical
  narrative_pacing:  slow | steady | accelerating | sprint
  pending_intent:    exploration | confrontation | revelation | recovery | transition

Rules:
- Cover a broad range of combinations — aim for maximum variety.
- Not all 5×4×4×5 = 400 combinations need to appear; ~50 is ideal.
- Each row must be unique (no duplicate combinations).
- entry_id must start at 0 and be sequential with no gaps.
- Do NOT include any narrative text, scene descriptions, or player-facing content.
  This palette is pure enumeration — it will be used as a classifier index at runtime.

Call generate_arc_palette exactly once with the complete list.
"""

_TOOL = {
    "name": "generate_arc_palette",
    "description": "Submit the complete arc-state palette (M2 Table A).",
    "input_schema": {
        "type": "object",
        "properties": {
            "entries": {
                "type": "array",
                "description": "List of arc state rows.",
                "items": {
                    "type": "object",
                    "properties": {
                        "entry_id": {"type": "integer"},
                        "arc_trajectory": {
                            "type": "string",
                            "enum": ["rising", "plateau", "climax", "resolution", "pivot"],
                        },
                        "world_pressure": {
                            "type": "string",
                            "enum": ["low", "moderate", "high", "critical"],
                        },
                        "narrative_pacing": {
                            "type": "string",
                            "enum": ["slow", "steady", "accelerating", "sprint"],
                        },
                        "pending_intent": {
                            "type": "string",
                            "enum": [
                                "exploration",
                                "confrontation",
                                "revelation",
                                "recovery",
                                "transition",
                            ],
                        },
                    },
                    "required": [
                        "entry_id",
                        "arc_trajectory",
                        "world_pressure",
                        "narrative_pacing",
                        "pending_intent",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["entries"],
        "additionalProperties": False,
    },
}


def generate(count: int = 50) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("SLOW_CORE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to .env or export it before running."
        )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Generate exactly {count} arc state entries covering a diverse range "
                    "of the four dimensions. Call generate_arc_palette with the complete list."
                ),
            }
        ],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "generate_arc_palette"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "generate_arc_palette":
            raw = block.input
            if isinstance(raw, str):
                raw = json.loads(raw)
            entries = raw["entries"]
            u = response.usage
            cost = _opus_cost(u.input_tokens, u.output_tokens)
            print(f"Generated {len(entries)} arc palette entries.")
            print(
                f"Usage — input: {u.input_tokens}  output: {u.output_tokens}  "
                f"cache_created: {getattr(u, 'cache_creation_input_tokens', 0)}  "
                f"cache_read: {getattr(u, 'cache_read_input_tokens', 0)}  "
                f"cost: ${cost:.4f}"
            )
            _md_log([
                f"## [{_ts()}] ARC PALETTE GENERATED",
                f"model: claude-opus-4-6",
                f"entries: {len(entries)}",
                f"tokens — input: {u.input_tokens}  output: {u.output_tokens}",
                f"cost: ${cost:.4f}",
                "dimensions: arc_trajectory × world_pressure × narrative_pacing × pending_intent",
            ])
            return entries

    raise RuntimeError("Claude did not call generate_arc_palette — no tool_use block found.")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate T2 cache (global arc-state palette).")
    parser.add_argument("--count", type=int, default=50, help="Target number of entries (default: 50).")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON path.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing palette without prompting.")
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        print(f"Arc palette already exists at {args.output}. Use --force to regenerate.")
        import sys; sys.exit(0)

    entries = generate(count=args.count)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
