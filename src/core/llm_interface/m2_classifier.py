"""M2 arc-state classifier — runtime Claude call (per-choice).

Called after each player choice to:
  1. Classify the current arc state → best-fit Table A entry_id
  2. Assign per-option effect values for the NEXT arbitration in the current node

Cache structure (Anthropic prompt-cache prefix):
  system    — arc classification guide       ~3,000 tokens  (global, cached)
  tool      — select_arc_and_effects schema  ~1,000 tokens  (global, cached)
  user[0]   — Table A                        ~1,500 tokens  (session, cached)
  user[1]   — Table C (option structure)     ~2,000 tokens  (per-campaign, cached)
  user[2]   — quasi state + target arb hint  ~200-400 tokens (dynamic, uncached)

Token budget per call (after cache warm):
  Input  (cached):   system + tool + Table A + Table C  ~5,000 tokens @ 0.1× rate
  Input  (dynamic):  quasi state + arb hint              ~300 tokens @ 1× rate
  Output:            entry_id + per-option effects        ~80-120 tokens
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import anthropic

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the runtime intelligence layer for a narrative game engine.
You have two jobs — both handled in a single tool call:

JOB 1 — ARC STATE CLASSIFICATION
Receive Table A (arc state catalogue) and the current game state.
Select the Table A entry_id that best matches the current arc state.

Selection rules:
- Match arc_trajectory first (rising/plateau/climax/resolution/pivot).
- Then world_pressure (low/moderate/high/critical).
- Then narrative_pacing and pending_intent as tiebreakers.
- If no row is a reasonable match, pass entry_id = -1.

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

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

JOB 2 — EFFECT ASSIGNMENT
You will be told which specific arbitration comes next: node_id + arb_index.
Look up that arbitration in Table C (per-campaign option structure).
Assign h/m/s integer values for every option in THAT ONE arbitration only.

Effect fields:
  h  health_delta   — typically -10 to +5.  Negative = injury, illness, exhaustion.
  m  money_delta    — typically -8 to +10.  Negative = cost, theft, loss.
  s  sanity_delta   — typically -8 to +3.   Negative = dread, trauma, revelation.

Calibration rules:
- Scale magnitude to current world_pressure: low → small values, critical → large negatives.
- Every arbitration must have at least one option with meaningfully different risk than others.
- 0 is valid (no effect on that stat).
- Positive values should feel earned — recovery, reward, relief.
- If no next arbitration is specified, output an empty effects list.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

_NO_MATCH_ID = -1


@dataclass
class M2ClassifierConfig:
    api_key: str | None = None
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 150   # entry_id + one arb's per-option effects
    timeout: float = 30.0


class M2Classifier:
    """Classifies current game arc state and assigns per-option effects for the next arbitration.

    Called once per player choice (after each arbitration completes). The call is
    fire-and-forget — results are consumed before the next arbitration is displayed.
    """

    def __init__(
        self,
        config: M2ClassifierConfig | None = None,
        table_a_json: str = "[]",
        table_c_json: str = "",
    ) -> None:
        self._cfg = config or M2ClassifierConfig()
        self._table_a_json = table_a_json
        self._table_c_json = table_c_json
        self._client = anthropic.AsyncAnthropic(api_key=self._cfg.api_key)

        self._tool = {
            "name": "select_arc_and_effects",
            "description": (
                "Select the best-matching Table A arc state and assign per-option "
                "gameplay effect values for the specified next arbitration."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "entry_id": {
                        "type": "integer",
                        "description": (
                            "The entry_id of the best-matching Table A row, "
                            "or -1 if no row is a reasonable match."
                        ),
                    },
                    "effects": {
                        "type": "array",
                        "description": (
                            "Per-option effect values for every option in the specified "
                            "next arbitration. Empty array if no next arbitration was given."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "option_id from Table C.",
                                },
                                "h": {"type": "integer", "description": "health_delta"},
                                "m": {"type": "integer", "description": "money_delta"},
                                "s": {"type": "integer", "description": "sanity_delta"},
                            },
                            "required": ["id", "h", "m", "s"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["entry_id", "effects"],
                "additionalProperties": False,
            },
            # Cache the tool schema alongside Table A for maximum prefix reuse
            "cache_control": {"type": "ephemeral"},
        }

    async def classify(
        self,
        quasi_state: str,
        next_node_id: str | None = None,
        next_arb_idx: int | None = None,
    ) -> tuple[int, dict[str, dict], dict[str, int]]:
        """Classify arc state and assign effects for the next arbitration.

        Args:
            quasi_state:   Current game state description (from build_classifier_input).
            next_node_id:  Campaign node_id the next arbitration belongs to.
            next_arb_idx:  0-based index of the next arbitration within that node.
                           Pass None (or omit) when there is no next arbitration
                           (last arb of a node → only entry_id is needed).

        Returns:
            (entry_id, effects_map, usage)
            effects_map: {option_id: {"health_delta": int, "money_delta": int, "sanity_delta": int}}
            Empty dict when next_node_id / next_arb_idx are not provided.
        """
        _empty_usage: dict[str, int] = {
            "input": 0, "output": 0, "cache_created": 0, "cache_read": 0
        }
        try:
            user_blocks: list[dict] = [
                # Block 1: Table A — stable for entire session, global cache
                {
                    "type": "text",
                    "text": f"Table A (arc state catalogue):\n{self._table_a_json}",
                    "cache_control": {"type": "ephemeral"},
                },
            ]

            # Block 2: Table C — per-campaign cache (only if loaded)
            if self._table_c_json:
                user_blocks.append({
                    "type": "text",
                    "text": f"Table C (node option structure for this campaign, no effect values):\n{self._table_c_json}",
                    "cache_control": {"type": "ephemeral"},
                })

            # Block 3: dynamic per-call content
            if next_node_id is not None and next_arb_idx is not None:
                arb_hint = (
                    f"\n\nAssign effects for: node_id={next_node_id}, arb_index={next_arb_idx}"
                )
            else:
                arb_hint = "\n\nNo next arbitration — output empty effects list."

            user_blocks.append({
                "type": "text",
                "text": quasi_state + arb_hint,
            })

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
                messages=[{"role": "user", "content": user_blocks}],
                tools=[self._tool],
                tool_choice={"type": "tool", "name": "select_arc_and_effects"},
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
                if block.type == "tool_use" and block.name == "select_arc_and_effects":
                    raw = block.input
                    if isinstance(raw, str):
                        raw = json.loads(raw)
                    entry_id = int(raw.get("entry_id", _NO_MATCH_ID))

                    # Parse flat effects list → {option_id: {health_delta, money_delta, sanity_delta}}
                    effects_map: dict[str, dict] = {}
                    for item in raw.get("effects", []):
                        opt_id = str(item.get("id", ""))
                        if opt_id:
                            effects_map[opt_id] = {
                                "health_delta":  int(item.get("h", 0)),
                                "money_delta":   int(item.get("m", 0)),
                                "sanity_delta":  int(item.get("s", 0)),
                            }

                    log.info(
                        "M2Classifier: entry_id=%d effects for %d option(s)",
                        entry_id, len(effects_map),
                    )
                    return entry_id, effects_map, usage

            log.warning("M2Classifier: no tool_use block in response")
            return _NO_MATCH_ID, {}, usage

        except Exception as exc:
            log.error("M2Classifier: classification failed: %s", exc)
            return _NO_MATCH_ID, {}, _empty_usage

    def update_table_a(self, table_a_json: str) -> None:
        """Replace the cached Table A JSON (e.g. after offline regeneration)."""
        self._table_a_json = table_a_json

    def update_table_c(self, table_c_json: str) -> None:
        """Replace the cached Table C JSON (e.g. after campaign switch)."""
        self._table_c_json = table_c_json
