"""C1 transport layer — ollama /api/chat HTTP client."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)


@dataclass
class C1Config:
    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434"
    timeout: float = 120.0
    max_retries: int = 2
    lang: str = "en"
    tone: str | None = None


async def call_ollama(
    prompt: str,
    cfg: C1Config,
    system_prompt: str,
    num_predict: int = -1,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Call ollama /api/chat with JSON mode.

    Returns (parsed_json, usage) where usage has keys prompt_tokens / eval_tokens.
    """
    url = f"{cfg.base_url}/api/chat"
    body = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.7,
            "num_predict": -1,
        },
    }

    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()

    data = resp.json()
    usage: dict[str, int] = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "eval_tokens": data.get("eval_count", 0),
    }
    msg = data.get("message")
    if not isinstance(msg, dict) or "content" not in msg:
        raise ValueError(
            f"Unexpected ollama response structure — keys={list(data.keys())} "
            f"(model not loaded or OOM?)"
        )
    raw_content = msg["content"]
    log.debug("C1 raw content length=%d", len(raw_content))

    json_start = raw_content.find("{")
    if json_start < 0:
        raise ValueError(f"No JSON object found in response (len={len(raw_content)})")
    if json_start > 0:
        log.debug("C1: stripping %d chars of reasoning prefix", json_start)
    json_end = raw_content.rfind("}")
    if json_end < json_start:
        raise ValueError(
            f"No closing '}}' found after opening '{{' in response (len={len(raw_content)}) — truncated output?"
        )
    content = raw_content[json_start:json_end + 1]
    return json.loads(content), usage
