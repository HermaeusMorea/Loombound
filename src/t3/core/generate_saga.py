#!/usr/bin/env python3
"""Generate a Loombound saga.

Step 1: Claude Opus generates the saga graph (waypoint topology, labels, map_blurbs).
Step 2: Claude Haiku generates T1 cache — scene skeletons for every waypoint (batch, one call).

Both steps run automatically. Use --skip-t1-cache to stop after Step 1.

Usage:
    python -m src.t3.core.generate_saga "drowned city cult investigation"
    python -m src.t3.core.generate_saga "lighthouse keeper's descent" --nodes 8
    python -m src.t3.core.generate_saga "渔村诅咒" --lang zh --nodes 6
    python -m src.t3.core.generate_saga "solar archaeology" --tone "dirty political thriller"
    python -m src.t3.core.generate_saga "theme" --provider deepseek
    python -m src.t3.core.generate_saga "theme" --skip-t1-cache
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import anthropic

from src.shared.dotenv import load_dotenv
from src.shared.llm_utils import ts as _ts, md_log as _md_log, extract_tool_input as _extract_tool_input
from src.t2.core.gen_a1_cache_table import generate_scene_skeletons_step
from src.t3.core.saga_prompt import (
    _SYSTEM_PROMPT,
    _TOOL,
    _build_user_msg,
    _haiku_cost,
    _opus_cost,
)
from src.t3.core.saga_validate import _normalise, validate_graph
from src.t3.core.saga_write import print_graph, write_saga


def _log_saga_core_usage(
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
        f"## [{_ts()}] SAGA CORE RESPONSE — `{saga_id}`",
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
# Saga graph generation — Anthropic (Opus)
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
        tool_choice={"type": "tool", "name": "create_saga"},
    )

    u = response.usage
    print(f"  Usage: input={u.input_tokens}  output={u.output_tokens}  "
          f"(~${_opus_cost(u.input_tokens, u.output_tokens):.4f})")

    raw = _extract_tool_input(response, "create_saga")
    _log_saga_core_usage(
        provider="anthropic", model=model, theme=theme,
        node_count=node_count, lang=lang,
        tone_hint=tone_hint, worldview_hint=worldview_hint,
        saga_id=raw["saga_id"],
        title=raw.get("title", raw["saga_id"]),
        usage_input=u.input_tokens,
        usage_output=u.output_tokens,
    )
    return raw


# ---------------------------------------------------------------------------
# Step helpers (called from main)
# ---------------------------------------------------------------------------

def _step1_generate_graph(
    args: argparse.Namespace,
    model: str,
    api_key: str,
) -> dict:
    """Generate and validate the saga graph, retrying up to args.retries times."""
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
    load_dotenv()

    parser = argparse.ArgumentParser(description="Generate a Loombound saga.")
    parser.add_argument(
        "theme",
        nargs="?",
        default="drowned city cult investigation",
        help="Saga theme (default: 'drowned city cult investigation')",
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

    anthropic_key = None if args.skip_t1_cache else api_key

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
    out_path, node_count = write_saga(data, out_name, generation_context=generation_context)

    print(f"\n  Written: {out_path} ({node_count} nodes inlined)")

    # ── Step 2: generate T1 cache (Haiku, batched 3 nodes per call) ────────

    if not args.skip_t1_cache and anthropic_key:
        generate_scene_skeletons_step(data, node_count, args.lang, anthropic_key)

    saga_id = data['saga_id']
    print(f"\nSAGA_ID={saga_id}")
    print(f"SAGA_PATH={out_path}")
    print(f"\nTo play:")
    print(f"  ./loombound run --saga {saga_id} --lang {args.lang}")


if __name__ == "__main__":
    main()
