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

import logging
from dataclasses import dataclass

import anthropic

from src.shared import config
from src.shared.llm_utils import extract_tool_input as _extract_tool_input
from .m2_context import build_m2_context

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the runtime intelligence layer for a narrative game engine.
You have two jobs — both handled in a single tool call:

JOB 1 — ARC STATE CLASSIFICATION
Receive the T2 cache (arc state catalogue) and the current game state.
Select the T2 cache entry_id that best matches the current arc state.

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
Step 6. Scan the T2 cache for the entry whose four fields most closely match your assessment.
        Prefer exact matches on trajectory and pressure; use pacing and intent as
        tiebreakers. If no entry is within two dimensions of a match, return -1.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

JOB 2 — RULE SELECTION
You will also be given the saga's rule list. Each rule has an id, a name, a set of
decision_types, and a natural-language description of when it should apply.

Select the rule whose intent best matches the next encounter's scene type and the
current arc state. Output its id as selected_rule_id.

Selection criteria:
- The rule's decision_types should include the next encounter's scene_type.
- The rule's intent should fit the current world_pressure and arc_trajectory.
- If no rule is a reasonable fit, output selected_rule_id = "".
- If no next encounter is specified, output selected_rule_id = "".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

JOB 3 — EFFECT ASSIGNMENT
You will be told which specific encounter comes next: node_id + arb_index.
Look up that encounter in Table C (per-saga option structure).
Assign h/m/s integer values for every option in THAT ONE encounter only.

Effect fields:
  h  health_delta   — typically -10 to +5.  Negative = injury, illness, exhaustion.
  m  money_delta    — typically -8 to +10.  Negative = cost, theft, loss.
  s  sanity_delta   — typically -8 to +3.   Negative = dread, trauma, revelation.

For each option, assign toll FIRST from the saga toll lexicon, then set h/m/s
values that are consistent with that toll. The toll lexicon is appended to
the A1 option index. Honor its numeric constraints — do not assign stable to an option
with large negative deltas, or destabilizing to an option with net positive deltas.

Calibration rules:
- Scale magnitude to current world_pressure: low → small values, critical → large negatives.
- Every encounter must have at least one option with meaningfully different risk than others.
- 0 is valid (no effect on that stat).
- Positive values should feel earned — recovery, reward, relief.
- If no next encounter is specified, output an empty effects list.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
        config: M2DecisionConfig | None = None,
        arc_state_catalog_json: str = "[]",
        scene_option_index_json: str = "",
        toll_lexicon_json: str = "",
        rules_json: str = "",
    ) -> None:
        self._cfg = config or M2DecisionConfig()
        self._arc_state_catalog_json = arc_state_catalog_json
        self._scene_option_index_json = scene_option_index_json
        self._toll_lexicon_json = toll_lexicon_json
        self._rules_json = rules_json
        self._client = anthropic.AsyncAnthropic(api_key=self._cfg.api_key)

        self._tool = {
            "name": "select_arc_and_effects",
            "description": (
                "Select the best-matching T2 cache arc state, select the most fitting "
                "saga rule, and assign per-option gameplay effect values for the next encounter."
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
                    "selected_rule_id": {
                        "type": "string",
                        "description": (
                            "The id of the saga rule that best fits the next encounter "
                            "and current arc state. Empty string if no rule fits or no "
                            "next encounter was specified."
                        ),
                    },
                    "effects": {
                        "type": "array",
                        "description": (
                            "Per-option effect values for every option in the specified "
                            "next encounter. Empty array if no next encounter was given."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "option_id from T1 option index.",
                                },
                                "v": {
                                    "type": "string",
                                    "description": "toll id from the saga toll lexicon. Assign this first, then set h/m/s consistent with it.",
                                },
                                "h": {"type": "integer", "description": "health_delta", "minimum": config.HEALTH_DELTA_MIN, "maximum": config.HEALTH_DELTA_MAX},
                                "m": {"type": "integer", "description": "money_delta",  "minimum": config.MONEY_DELTA_MIN,  "maximum": config.MONEY_DELTA_MAX},
                                "s": {"type": "integer", "description": "sanity_delta", "minimum": config.SANITY_DELTA_MIN, "maximum": config.SANITY_DELTA_MAX},
                            },
                            "required": ["id", "v", "h", "m", "s"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["entry_id", "selected_rule_id", "effects"],
                "additionalProperties": False,
            },
            # Cache the tool schema alongside T2 cache for maximum prefix reuse
            "cache_control": {"type": "ephemeral"},
        }

    @staticmethod
    def _parse_effects(raw: dict) -> tuple[int, str, dict[str, dict]] | None:
        """Parse and validate tool output. Returns None if format is invalid."""
        try:
            entry_id = int(raw.get("entry_id", _NO_MATCH_ID))
            selected_rule_id = str(raw.get("selected_rule_id", ""))
            effects_map: dict[str, dict] = {}
            for item in raw.get("effects", []):
                opt_id = str(item.get("id", ""))
                v = str(item.get("v", ""))
                if not opt_id or not v:
                    return None
                effects_map[opt_id] = {
                    "health_delta": max(config.HEALTH_DELTA_MIN, min(config.HEALTH_DELTA_MAX, int(item["h"]))),
                    "money_delta":  max(config.MONEY_DELTA_MIN,  min(config.MONEY_DELTA_MAX,  int(item["m"]))),
                    "sanity_delta": max(config.SANITY_DELTA_MIN, min(config.SANITY_DELTA_MAX, int(item["s"]))),
                    "toll":         v,
                }
            return entry_id, selected_rule_id, effects_map
        except (KeyError, TypeError, ValueError):
            return None

    async def classify(
        self,
        quasi_state: str,
        next_waypoint_id: str | None = None,
        next_arb_idx: int | None = None,
    ) -> tuple[int, str, dict[str, dict], dict[str, int]]:
        """Classify arc state, select a rule, and assign effects for the next encounter.

        Retries up to 2 times if the response fails format validation.
        Returns (entry_id, selected_rule_id, effects_map, usage).
        selected_rule_id is "" when no rule fits or no next encounter is specified.
        effects_map is empty when no next encounter is specified or retries exhausted.
        """
        _empty_usage: dict[str, int] = {
            "input": 0, "output": 0, "cache_created": 0, "cache_read": 0
        }

        needs_effects = next_waypoint_id is not None and next_arb_idx is not None
        arb_hint = (
            f"\n\nAssign effects for: waypoint_id={next_waypoint_id}, arb_index={next_arb_idx}"
            if needs_effects else
            "\n\nNo next encounter — output empty effects list and empty selected_rule_id."
        )

        bundle = build_m2_context(
            arc_state_catalog_json=self._arc_state_catalog_json,
            scene_option_index_json=self._scene_option_index_json,
            rules_json=self._rules_json,
            toll_lexicon_json=self._toll_lexicon_json,
            quasi_state=quasi_state,
            arb_hint=arb_hint,
        )

        _MAX_RETRIES = config.M2_MAX_RETRIES
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._client.messages.create(
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": bundle.to_user_content()}],
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
                    "M2DecisionEngine: input=%d cache_created=%d cache_read=%d output=%d (attempt %d)",
                    u.input_tokens, cache_created, cache_read, u.output_tokens, attempt + 1,
                )

                try:
                    raw = _extract_tool_input(response, "select_arc_and_effects")
                except RuntimeError:
                    log.warning("M2DecisionEngine: no tool call on attempt %d, retrying", attempt + 1)
                    continue

                parsed = self._parse_effects(raw)
                if parsed is None and needs_effects:
                    log.warning("M2DecisionEngine: invalid format on attempt %d, retrying", attempt + 1)
                    continue
                entry_id, rule_id, effects_map = parsed if parsed else (_NO_MATCH_ID, "", {})
                log.info(
                    "M2DecisionEngine: entry_id=%d rule=%r effects for %d option(s)",
                    entry_id, rule_id, len(effects_map),
                )
                return entry_id, rule_id, effects_map, usage

            except Exception as exc:
                log.error("M2DecisionEngine: attempt %d failed: %s", attempt + 1, exc)
                if attempt == _MAX_RETRIES:
                    return _NO_MATCH_ID, "", {}, _empty_usage

        return _NO_MATCH_ID, "", {}, _empty_usage

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
