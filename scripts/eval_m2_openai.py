#!/usr/bin/env python3
"""Evaluate a small OpenAI-compatible model on dumped M2 classifier calls.

Workflow:
  1. Play a V1 session with M2_DUMP_PATH=/tmp/m2_dump.jsonl set — the M2
     decision engine will append one jsonl record per call.
  2. Run this script to replay each record against a smaller model and
     report agreement rates against the Haiku baseline.

Usage:
    export OPENAI_API_KEY=...         # from .env
    python scripts/eval_m2_openai.py /tmp/m2_dump.jsonl --model gpt-5.4-nano
    python scripts/eval_m2_openai.py /tmp/m2_dump.jsonl --model deepseek-chat \\
        --base-url https://api.deepseek.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src.shared.dotenv import load_dotenv

load_dotenv()


def _to_openai_tool(anth_tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": anth_tool["name"],
            "description": anth_tool.get("description", ""),
            "parameters": anth_tool["input_schema"],
        },
    }


def _call_openai(client, model: str, record: dict) -> dict | None:
    tool = _to_openai_tool(record["tool_schema"])
    user_text = "\n\n".join(record["user_blocks"])
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": record["system"]},
            {"role": "user", "content": user_text},
        ],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
    )
    msg = resp.choices[0].message
    if not getattr(msg, "tool_calls", None):
        return None
    try:
        return json.loads(msg.tool_calls[0].function.arguments)
    except json.JSONDecodeError:
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("dump_path", type=Path, help="jsonl file from M2_DUMP_PATH")
    p.add_argument("--model", required=True, help="Model id, e.g. gpt-5.4-nano")
    p.add_argument("--base-url", default=None, help="Override base URL for compat providers")
    p.add_argument("--limit", type=int, default=None, help="Max records to evaluate")
    args = p.parse_args(argv)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.stderr.write("OPENAI_API_KEY not set (check .env)\n")
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        sys.stderr.write("openai package missing. Run: pip install openai\n")
        return 1

    client_kwargs: dict = {"api_key": api_key}
    if args.base_url:
        client_kwargs["base_url"] = args.base_url
    client = OpenAI(**client_kwargs)

    total = 0
    failures = 0
    entry_match = 0
    rule_match = 0
    effects_total = 0
    effects_toll_match = 0
    effects_abs_err = {"h": 0, "m": 0, "s": 0}
    effects_abs_samples = 0

    with args.dump_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if args.limit and total >= args.limit:
                break
            record = json.loads(line)

            try:
                nano_out = _call_openai(client, args.model, record)
            except Exception as exc:
                sys.stderr.write(f"[line {line_no}] API error: {exc}\n")
                failures += 1
                continue

            total += 1
            if nano_out is None:
                failures += 1
                sys.stderr.write(f"[line {line_no}] no tool call returned\n")
                continue

            haiku = record["haiku_parsed"]
            haiku_entry = haiku["entry_id"]
            # Step 2 dumps no longer carry selected_rule_id / effects — those
            # are handled by symbolic rule_selector and effects_templater.
            haiku_rule = haiku.get("selected_rule_id")
            haiku_effects = haiku.get("effects", {}) or {}

            nano_entry = nano_out.get("entry_id")
            nano_rule = str(nano_out.get("selected_rule_id", ""))

            if nano_entry == haiku_entry:
                entry_match += 1
            else:
                sys.stderr.write(
                    f"[line {line_no}] entry_id  haiku={haiku_entry}  nano={nano_entry}\n"
                )
            # Only score rule_id if both sides produced one (legacy dumps).
            if haiku_rule is not None and nano_rule == haiku_rule:
                rule_match += 1

            # Only score effects if legacy dumps carry them.
            if haiku_effects:
                for item in nano_out.get("effects", []) or []:
                    opt_id = str(item.get("id", ""))
                    if not opt_id:
                        continue
                    effects_total += 1
                    base = haiku_effects.get(opt_id)
                    if not base:
                        continue
                    if str(item.get("v", "")) == base.get("toll"):
                        effects_toll_match += 1
                    try:
                        effects_abs_err["h"] += abs(int(item.get("h", 0)) - int(base.get("health_delta", 0)))
                        effects_abs_err["m"] += abs(int(item.get("m", 0)) - int(base.get("money_delta", 0)))
                        effects_abs_err["s"] += abs(int(item.get("s", 0)) - int(base.get("sanity_delta", 0)))
                        effects_abs_samples += 1
                    except (TypeError, ValueError):
                        pass

    def pct(num, denom):
        return f"{100 * num / denom:.1f}%" if denom else "n/a"

    def avg(num, denom):
        return f"{num / denom:.2f}" if denom else "n/a"

    print("=" * 60)
    print(f"Model:           {args.model}")
    if args.base_url:
        print(f"Base URL:        {args.base_url}")
    print(f"Dump:            {args.dump_path}")
    print(f"Records scored:  {total}")
    print(f"API failures:    {failures}")
    print("-" * 60)
    print(f"entry_id match:  {entry_match}/{total}  ({pct(entry_match, total)})")
    # Legacy dump fields — only print when there was something to score.
    if rule_match or (total and effects_total):
        print(f"rule_id  match:  {rule_match}/{total}  ({pct(rule_match, total)})")
    if effects_total:
        print(f"toll     match:  {effects_toll_match}/{effects_total}  ({pct(effects_toll_match, effects_total)})")
        print(f"avg |h-err|:     {avg(effects_abs_err['h'], effects_abs_samples)}")
        print(f"avg |m-err|:     {avg(effects_abs_err['m'], effects_abs_samples)}")
        print(f"avg |s-err|:     {avg(effects_abs_err['s'], effects_abs_samples)}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
