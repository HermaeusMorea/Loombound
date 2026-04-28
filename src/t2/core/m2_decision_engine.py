"""M2 decision engine — runtime Claude call (per-choice).

Called after each player choice to:
  1. Classify the current arc state → best-fit arc-state catalog entry_id
  2. Assign per-option effect values for the NEXT encounter in the current waypoint

Cache structure (Anthropic prompt-cache prefix):
  system    — arc classification guide       ~3,000 tokens  (global, cached)
  tool      — select_arc_and_effects schema  ~1,000 tokens  (global, cached)
  user[0]   — T2 cache (arc palette)         ~1,500 tokens  (session, cached)
  user[1]   — T1 option index                ~2,000 tokens  (per-saga, cached)
  user[2]   — quasi state + target arb hint  ~200-400 tokens (dynamic, uncached)

Token budget per call (after cache warm):
  Input  (cached):   system + tool + T2 cache + T1 option index  ~5,000 tokens @ 0.1× rate
  Input  (dynamic):  quasi state + arb hint                       ~300 tokens @ 1× rate
  Output:            entry_id + per-option effects                  ~80-120 tokens
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic

from src.shared import config
from src.shared.llm_utils import extract_tool_input as _extract_tool_input
from .m2_context import build_m2_context

log = logging.getLogger(__name__)

_M2_DUMP_PATH = os.environ.get("M2_DUMP_PATH")


def _strip_cache_control(obj):
    if isinstance(obj, dict):
        return {k: _strip_cache_control(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [_strip_cache_control(v) for v in obj]
    return obj

_SYSTEM_PROMPT = """\
You are the runtime arc-state classifier for a narrative game engine.
You have ONE job: pick the one catalog entry whose narrative stage best
matches the current game state. Output only `entry_id`.

HOW TO PICK

1. Read the quasi_state. Mentally summarize the narrative situation in
   one sentence: Is the protagonist just starting out? Investigating a
   mystery? Stalled at an obstacle? Facing a climax? Recovering from
   a shock? About to cross a threshold?

2. Scan the catalog. Each entry has a `label` (short tag like
   `opening_stable`, `pressure_mounting`, `pivot_reversal`) and a 2–3
   sentence `description` that paints the narrative stage. The four
   dimension fields (arc_trajectory / world_pressure / narrative_pacing
   / pending_intent) are secondary metadata — use them only as
   tiebreakers between descriptions that feel similarly applicable.

3. Pick the single entry whose `description` most closely fits the
   situation you summarized. Output its `entry_id`.

4. Return -1 only if NONE of the descriptions is even loosely
   applicable to the state (truly anomalous). In practice this should
   be rare — the catalog aims to cover the full arc of any run.

QUICK REFERENCE FOR READING quasi_state

- `health/money/sanity` bands (very_low ... very_high) + direction
  (rising/falling/stable) = the protagonist's physical and mental
  resourcing.
- `dominant themes` = recurring emotional colour.
- `Recent incidents` and `Waypoint trajectory` = what just happened
  and the trend. Low depth + few events = probably opening. High
  depth + heavy losses = probably climax or survival. Pivots /
  revelations leave distinct marks in the events log.
- Low pressure + slow pacing + no heavy events ⇒ opening or
  aftermath; differentiate by depth.
- High depth + escalating events ⇒ climax zone.

Bias:
- Do NOT over-return -1. If the situation vaguely resembles a catalog
  description, pick it. The embedding layer and downstream templater
  tolerate imperfect matches far better than they tolerate empty
  classifications.
"""

_NO_MATCH_ID = -1


@dataclass
class M2DecisionConfig:
    api_key: str | None = None
    model: str = config.M2_MODEL
    max_tokens: int = config.M2_MAX_TOKENS
    timeout: float = config.M2_TIMEOUT


class M2DecisionEngine:
    """Classifies current game arc state and assigns per-option effects for the next encounter.

    Called once per player choice (after each encounter completes). The call is
    fire-and-forget — results are consumed before the next encounter is displayed.
    """

    def __init__(
        self,
        cfg: M2DecisionConfig | None = None,
        arc_state_catalog_json: str = "[]",
        scene_option_index_json: str = "",
        toll_lexicon_json: str = "",
        rules_json: str = "",
    ) -> None:
        self._cfg = cfg or M2DecisionConfig()
        self._arc_state_catalog_json = arc_state_catalog_json
        self._scene_option_index_json = scene_option_index_json
        self._toll_lexicon_json = toll_lexicon_json
        self._rules_json = rules_json
        self._client = anthropic.AsyncAnthropic(api_key=self._cfg.api_key)

        self._tool = {
            "name": "select_arc",
            "description": (
                "Select the best-matching T2 cache arc state entry for the current game state."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "description": (
                            "The entry_id of the best-matching T2 cache entry, "
                            "or -1 if no entry is a reasonable match."
                        ),
                    },
                },
                "required": ["entry_id"],
                "additionalProperties": False,
            },
            # Cache the tool schema alongside T2 cache for maximum prefix reuse
            "cache_control": {"type": "ephemeral"},
        }

    @staticmethod
    def _parse_tool_output(raw: dict) -> int | None:
        """Parse and validate tool output. Returns None if format is invalid."""
        try:
            return int(raw.get("entry_id", _NO_MATCH_ID))
        except (TypeError, ValueError):
            return None

    def _dump_call(
        self,
        *,
        bundle,
        next_waypoint_id: str | None,
        next_arb_idx: int | None,
        raw: dict,
        entry_id: int,
        usage: dict,
    ) -> None:
        if not _M2_DUMP_PATH:
            return
        try:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": self._cfg.model,
                "system": _SYSTEM_PROMPT,
                "user_blocks": [b.get("text", "") for b in bundle.to_user_content()],
                "tool_name": self._tool["name"],
                "tool_schema": _strip_cache_control(self._tool),
                "next_waypoint_id": next_waypoint_id,
                "next_arb_idx": next_arb_idx,
                "haiku_raw": raw,
                "haiku_parsed": {"entry_id": entry_id},
                "usage": usage,
            }
            with open(_M2_DUMP_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            log.warning("M2DecisionEngine: dump failed: %s", exc)

    async def classify(
        self,
        quasi_state: str,
        next_waypoint_id: str | None = None,
        next_arb_idx: int | None = None,
    ) -> tuple[int, dict[str, int]]:
        """Classify arc state for the current game snapshot.

        Retries up to 2 times if the response fails format validation.
        Returns (entry_id, usage). next_waypoint_id / next_arb_idx are retained
        only for log / dump context — rule selection and effects are handled
        downstream.
        """
        _empty_usage: dict[str, int] = {
            "input": 0, "output": 0, "cache_created": 0, "cache_read": 0
        }

        arb_hint = (
            f"\n\nClassify arc state ahead of: waypoint_id={next_waypoint_id}, arb_index={next_arb_idx}"
            if next_waypoint_id is not None and next_arb_idx is not None
            else "\n\nClassify current arc state."
        )

        bundle = build_m2_context(
            arc_state_catalog_json=self._arc_state_catalog_json,
            scene_option_index_json=self._scene_option_index_json,
            rules_json=self._rules_json,
            toll_lexicon_json=self._toll_lexicon_json,
            quasi_state=quasi_state,
            arb_hint=arb_hint,
        )

        tool_name = self._tool["name"]
        _MAX_RETRIES = config.M2_MAX_RETRIES
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._client.messages.create(
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": bundle.to_user_content()}],
                    tools=[self._tool],
                    tool_choice={"type": "tool", "name": tool_name},
                )

                u = response.usage
                cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
                cache_created = getattr(u, "cache_creation_input_tokens", 0) or 0
                usage = {
                    "input": u.input_tokens,
                    "output": u.output_tokens,
                    "cache_created": cache_created,
                    "cache_read": cache_read,
                }
                log.info(
                    "M2DecisionEngine: input=%d cache_created=%d cache_read=%d output=%d (attempt %d)",
                    u.input_tokens, cache_created, cache_read, u.output_tokens, attempt + 1,
                )

                try:
                    raw = _extract_tool_input(response, tool_name)
                except RuntimeError:
                    log.warning("M2DecisionEngine: no tool call on attempt %d, retrying", attempt + 1)
                    continue

                entry_id = self._parse_tool_output(raw)
                if entry_id is None:
                    log.warning("M2DecisionEngine: invalid format on attempt %d, retrying", attempt + 1)
                    continue
                log.info("M2DecisionEngine: entry_id=%d", entry_id)
                self._dump_call(
                    bundle=bundle,
                    next_waypoint_id=next_waypoint_id,
                    next_arb_idx=next_arb_idx,
                    raw=raw,
                    entry_id=entry_id,
                    usage=usage,
                )
                return entry_id, usage

            except Exception as exc:
                log.error("M2DecisionEngine: attempt %d failed: %s", attempt + 1, exc)
                if attempt == _MAX_RETRIES:
                    return _NO_MATCH_ID, _empty_usage

        return _NO_MATCH_ID, _empty_usage

    def update_arc_state_catalog(self, arc_state_catalog_json: str) -> None:
        """Replace the arc-state catalog JSON (e.g. after offline regeneration)."""
        self._arc_state_catalog_json = arc_state_catalog_json

    def update_scene_option_index(self, scene_option_index_json: str, toll_lexicon_json: str = "") -> None:
        """Replace the scene option index JSON and toll lexicon (e.g. after saga switch)."""
        self._scene_option_index_json = scene_option_index_json
        self._toll_lexicon_json = toll_lexicon_json

    def update_rules(self, rules_json: str) -> None:
        """Replace the saga rules JSON (e.g. after saga switch)."""
        self._rules_json = rules_json
