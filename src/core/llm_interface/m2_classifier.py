"""M2 arc-state classifier — runtime Claude call.

Receives Table A (cached in prompt) + current M1+M0 quasi state.
Returns a single integer entry_id matching the best-fit row in Table A,
or -1 if no row is a reasonable match (no-match fallback).

Token budget per call (after cache warm):
  Input  (cached):  system + tool + Table A  ~3,000 tokens @ 0.1× rate
  Input  (dynamic): quasi state description  ~200-400 tokens @ 1× rate
  Output:           {"entry_id": N}          ~10 tokens @ output rate
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import anthropic

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an arc-state classifier for a narrative game engine.

You receive:
1. A table of arc states (Table A) — each row has an entry_id and four categorical fields.
2. The current game state described in quasi-precise language (M1+M0 summary).

Your sole job is to call select_arc_state exactly once, passing the entry_id of the Table A row
that best matches the current game state.

Selection rules:
- Match arc_trajectory first (rising/plateau/climax/resolution/pivot).
- Then world_pressure (low/moderate/high/critical).
- Then narrative_pacing and pending_intent as tiebreakers.
- If no row is a reasonable match, pass entry_id = -1.

Do not produce any output outside the tool call.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARC STATE CLASSIFICATION GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIMENSION 1 — arc_trajectory
The overall narrative momentum of the run so far.

  rising        The protagonist's position, knowledge, or agency is expanding.
                Obstacles appear but are overcome. Resources accumulate.
                The world opens up. Confidence or determination increases.
                Signal words: discovery, momentum, escalation, growth, pursuit.

  plateau       Progress has leveled off. The protagonist holds a stable position
                but cannot easily advance or retreat. A period of assessment,
                negotiation, or waiting. Tension is present but not yet breaking.
                Signal words: stalemate, consolidation, uncertainty, delay, balance.

  climax        The decisive confrontation or revelation. Maximum pressure.
                Everything the run has built toward is now arriving simultaneously.
                Resources are depleted or committed. No safe exit. The outcome
                will define what follows.
                Signal words: crisis, convergence, threshold, culmination, peak.

  resolution    The major conflict has been decided. Aftermath, consequence, and
                integration. The protagonist processes what happened and moves
                toward a new equilibrium — positive, negative, or ambiguous.
                Signal words: aftermath, closure, reconciliation, grief, acceptance.

  pivot         An unexpected reversal has changed the run's direction entirely.
                A betrayal, revelation, or sudden shift that invalidates previous
                assumptions. The protagonist must reorient from scratch.
                Signal words: reversal, betrayal, revelation, reframe, rupture.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIMENSION 2 — world_pressure
The intensity of external forces acting on the protagonist.

  low           The environment is permissive. The protagonist can act without
                immediate threat. Exploration, contemplation, and preparation
                are viable. Mistakes are recoverable.

  moderate      Some opposition or constraint is present. The protagonist must
                be deliberate. Some actions are risky. The situation has stakes
                but not yet urgency.

  high          Active threat or crisis. The protagonist is under real pressure.
                Time or resources are limited. Errors have significant cost.
                Tension is felt in every scene beat.

  critical      Existential pressure. The protagonist is at the edge of failure,
                madness, or death. Every decision is high-stakes. The environment
                is actively hostile. Survival is not guaranteed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIMENSION 3 — narrative_pacing
How quickly events are moving in the current section of the run.

  slow          Scenes breathe. Information is revealed gradually. The player
                has time to absorb environment, lore, and character. Atmosphere
                dominates over action.

  steady        A measured forward movement. Events progress logically. No rush,
                but no stagnation. Standard adventure pacing.

  accelerating  The pace is increasing. Each scene triggers the next more
                urgently. Downtime is shrinking. The run is building toward
                something and the player can feel it.

  sprint        Maximum velocity. Back-to-back crises with no breathing room.
                Scenes are short and punchy. Every moment matters. Often
                accompanies climax or critical world_pressure.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIMENSION 4 — pending_intent
The nature of what the protagonist is about to do next.

  exploration   Seeking new information, locations, or relationships. The next
                action is investigative or expansive. Open-ended curiosity.

  confrontation A direct challenge, conflict, or negotiation with an opposing
                force. The protagonist is moving toward friction.

  revelation    A key truth is about to surface — through discovery, confession,
                or forced disclosure. Answers are coming, wanted or not.

  recovery      The protagonist is regrouping: healing, restoring resources,
                processing loss, or rebuilding after damage.

  transition    A threshold crossing. Moving between acts, locations, or
                identities. The current chapter is ending; the next is unknown.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MATCHING PROCEDURE

Step 1. Read the M1+M0 quasi state carefully.
Step 2. Identify the arc_trajectory that best describes the run's current momentum.
Step 3. Identify the world_pressure from environmental and threat signals.
Step 4. Identify the narrative_pacing from the density and urgency of recent events.
Step 5. Identify the pending_intent from what the protagonist is positioned to do next.
Step 6. Scan Table A for the row whose four fields most closely match your assessment.
        Prefer exact matches on trajectory and pressure; use pacing and intent as
        tiebreakers. If no row is within two dimensions of a match, return -1.
Step 7. Call select_arc_state with the chosen entry_id (or -1 for no match).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

_NO_MATCH_ID = -1


@dataclass
class M2ClassifierConfig:
    api_key: str | None = None
    model: str = "claude-opus-4-6"
    max_tokens: int = 64   # entry_id output is tiny
    timeout: float = 30.0


class M2Classifier:
    """Classifies current game arc state against Table A and returns entry_id."""

    def __init__(self, config: M2ClassifierConfig | None = None, table_a_json: str = "[]") -> None:
        self._cfg = config or M2ClassifierConfig()
        self._table_a_json = table_a_json
        self._client = anthropic.AsyncAnthropic(api_key=self._cfg.api_key)

        self._tool = {
            "name": "select_arc_state",
            "description": "Select the Table A entry_id that best matches the current arc state.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "description": (
                            "The entry_id of the best-matching Table A row, "
                            "or -1 if no row is a reasonable match."
                        ),
                    }
                },
                "required": ["entry_id"],
                "additionalProperties": False,
            },
            # Cache the tool schema alongside Table A for maximum prefix reuse
            "cache_control": {"type": "ephemeral"},
        }

    async def classify(self, quasi_state: str) -> tuple[int, dict[str, int]]:
        """Return (entry_id, usage) for the given quasi state.

        entry_id: best-matching Table A row, or -1 on no-match/error.
        usage: dict with keys input, output, cache_created, cache_read.
        """
        _empty_usage: dict[str, int] = {
            "input": 0, "output": 0, "cache_created": 0, "cache_read": 0
        }
        try:
            response = await self._client.messages.create(
                model=self._cfg.model,
                max_tokens=self._cfg.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            # Block 1: Table A — stable for entire session, cached
                            # Combined with system + tool: ~3,000 tokens > 2,048 Opus minimum
                            {
                                "type": "text",
                                "text": f"Table A (arc state catalogue):\n{self._table_a_json}",
                                "cache_control": {"type": "ephemeral"},
                            },
                            # Block 2: current M1+M0 quasi state — dynamic per node
                            {
                                "type": "text",
                                "text": quasi_state,
                            },
                        ],
                    }
                ],
                tools=[self._tool],
                tool_choice={"type": "tool", "name": "select_arc_state"},
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
                "M2Classifier: input=%d cache_created=%d cache_read=%d output=%d",
                u.input_tokens, cache_created, cache_read, u.output_tokens,
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == "select_arc_state":
                    raw = block.input
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    entry_id = int(raw.get("entry_id", _NO_MATCH_ID))
                    log.info("M2Classifier: classified → entry_id=%d", entry_id)
                    return entry_id, usage

            log.warning("M2Classifier: no tool_use block in response")
            return _NO_MATCH_ID, usage

        except Exception as exc:
            log.error("M2Classifier: classification failed: %s", exc)
            return _NO_MATCH_ID, _empty_usage

    def update_table_a(self, table_a_json: str) -> None:
        """Replace the cached Table A JSON (e.g. after offline regeneration)."""
        self._table_a_json = table_a_json
