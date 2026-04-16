"""Offline script: generate M2 Table A — arc state enumeration catalogue.

Calls Claude once to produce 40-60 rows of arc state combinations.
Each row has exactly 4 categorical fields + a stable entry_id.

Output: data/m2_table_a.json

Usage:
    python generate_table_a.py
    python generate_table_a.py --count 50 --output data/m2_table_a.json

Requires ANTHROPIC_API_KEY in environment or .env file.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).parent
ENV_PATH = REPO_ROOT / ".env"
OUTPUT_PATH = REPO_ROOT / "data" / "m2_table_a.json"


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
  Table A is pure enumeration — it will be filled with content separately.

Call generate_table_a exactly once with the complete list.
"""

_TOOL = {
    "name": "generate_table_a",
    "description": "Submit the complete Table A arc state catalogue.",
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
                    "of the four dimensions. Call generate_table_a with the complete list."
                ),
            }
        ],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "generate_table_a"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "generate_table_a":
            raw = block.input
            if isinstance(raw, str):
                raw = json.loads(raw)
            entries = raw["entries"]
            print(f"Generated {len(entries)} Table A entries.")
            u = response.usage
            print(
                f"Usage — input: {u.input_tokens}  output: {u.output_tokens}  "
                f"cache_created: {getattr(u, 'cache_creation_input_tokens', 0)}  "
                f"cache_read: {getattr(u, 'cache_read_input_tokens', 0)}"
            )
            return entries

    raise RuntimeError("Claude did not call generate_table_a — no tool_use block found.")


def main() -> None:
    _load_dotenv()

    parser = argparse.ArgumentParser(description="Generate M2 Table A arc state catalogue.")
    parser.add_argument("--count", type=int, default=50, help="Target number of entries (default: 50).")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON path.")
    args = parser.parse_args()

    entries = generate(count=args.count)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
