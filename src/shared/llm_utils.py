"""Shared LLM logging and cost utilities."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()

REPO_ROOT = (
    Path(os.environ["LOOMBOUND_ROOT"]).resolve()
    if os.environ.get("LOOMBOUND_ROOT")
    else Path(os.environ["BLACK_ARCHIVE_ROOT"]).resolve()
    if os.environ.get("BLACK_ARCHIVE_ROOT")
    else Path(__file__).resolve().parents[2]
)
LLM_LOG = REPO_ROOT / "logs" / "llm.md"

OPUS_INPUT_COST      = 5.0  / 1_000_000
OPUS_OUTPUT_COST     = 25.0 / 1_000_000
OPUS_CACHE_READ_COST = 0.50 / 1_000_000
HAIKU_INPUT_COST     = 0.80 / 1_000_000
HAIKU_OUTPUT_COST    = 4.0  / 1_000_000


def opus_cost(inp: int, out: int) -> float:
    return inp * OPUS_INPUT_COST + out * OPUS_OUTPUT_COST


def haiku_cost(inp: int, out: int) -> float:
    return inp * HAIKU_INPUT_COST + out * HAIKU_OUTPUT_COST


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def md_log(lines: list[str]) -> None:
    """Append a markdown block to LLM_LOG. Thread-safe, auto-creates parent dir."""
    block = "\n".join(lines) + "\n\n"
    with _lock:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LLM_LOG.open("a", encoding="utf-8") as f:
            f.write(block)


def coerce_json(raw: object) -> dict:
    """Normalise tool call output to plain dict (handles str and Pydantic models)."""
    if isinstance(raw, str):
        return json.loads(raw)
    return json.loads(json.dumps(raw))


def extract_tool_input(response: object, tool_name: str) -> dict:
    """Return the input dict from the first matching tool_use block.

    Raises RuntimeError if no matching block is found.
    """
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return coerce_json(block.input)
    stop = getattr(response, "stop_reason", "unknown")
    raise RuntimeError(f"No {tool_name!r} tool call in response. stop_reason={stop}")
