"""Prompt building and tool schema for Opus saga graph generation."""
from __future__ import annotations

from src.shared.llm_utils import opus_cost as _opus_cost, haiku_cost as _haiku_cost


_SYSTEM_PROMPT = """\
You are a saga designer for a text-adventure roguelite. Your sole job is to call \
create_saga exactly once with a complete, structurally valid saga based on the \
theme the user provides. Invent the tone, setting, and genre yourself — do not default \
to any particular aesthetic unless the theme clearly implies one.

─── SAGA DESIGN RULES ──────────────────────────────────────────────────────
NODE GRAPH
- All waypoint_ids referenced in any waypoint's next_waypoints MUST appear as a waypoint_id in your waypoints list.
- start_waypoint_id MUST be one of the waypoint_ids you define.
- At least one waypoint must have next_waypoints: [] (the terminal node — saga's climax).
- Depth must increase strictly along any path through the graph.
- Prefer branching over linear chains — at least one fork somewhere in the graph.

NODE TYPES  (use exactly one per node)
  crossroads   — pure navigation choice, minimal encounter
  market       — commerce, trade, dubious vendors
  encounter    — something dangerous or ambiguous in the environment
  archive      — information, forbidden knowledge, documents
  ritual       — ceremony, transformation, a turning point
  threshold    — a boundary crossing, a point of no return
  rest         — brief respite (keep encounters low: 1)
  investigation — detective work, evidence, secrets

ARBITRATION COUNT (integer, 1–3 per node)
  1  — brief node, single consequential moment
  2  — standard node, two linked scenes
  3  — major node, prolonged encounter

TONE FIELD
Write a 2–4 sentence description of the saga's genre, atmosphere, and aesthetic. \
This will be injected into the content generator for every waypoint. Be specific: name the \
genre, the mood, the kind of imagery that should recur. This is the single most \
important field for content coherence.

map_blurb: 1–2 sentences the player sees on the map. Specific and evocative.
intro: 2–3 sentences setting the whole saga's opening mood.

VERDICT DICTIONARY
Generate 3–6 saga-specific toll labels that describe option consequences.
- Always include "stable" (net delta ≥ 0) and "destabilizing" (net delta clearly negative).
- Add 1–4 theme-specific entries that fit your saga's tone (e.g. "cursed", "exploitative", "honorable", "corrupting").
- Each entry needs a one-line description of the numeric constraints it implies for h/m/s values.
- These labels will be used by the runtime AI to classify options before assigning numbers.

RULES
Generate 3–5 saga-specific rules that define the psychological logic of this world. \
Each rule is a pattern the protagonist should follow to maintain stability — a discipline, \
a survival heuristic, a moral code forged by this world's specific pressures.
- id: snake_case, descriptive (e.g. "rule_never_open_unmarked_doors")
- name: a short, memorable maxim phrased as guidance ("When the fog thickens, trust the cold")
- theme: must be one of the snake_case keys you define in narration_table
- decision_types: which scene types trigger this rule (crossroads, market, encounter, archive, ritual, threshold, rest, investigation)
- priority: 60–120 (higher = checked first)
- sanity_penalty: integer 0–3 (cost if the rule is violated)
- preferred_option_tags: tags on options this rule favors
- forbidden_option_tags: tags on options this rule forbids
- match (optional): resource bounds or required_context_tags that restrict when the rule fires \
  (max_health, min_health, max_money, min_money, max_sanity, min_sanity, required_context_tags)
Make the rules feel like they were written by someone who survived this world, not a game designer.

NARRATION TABLE
Define 10–15 psychological theme labels for this saga. Each entry is a snake_case key mapped \
to one sentence shown to the player after a choice — a brief internal state, mood, or sensation \
the protagonist feels at that moment of psychological pressure.
Rules:
- Write in second person ("You…" / "你…"). One sentence per theme, under 20 words.
- Describe inner experience only — no concrete actions, no invented specifics (no page numbers, \
  names, or locations).
- Must include a "neutral" key as the default fallback.
- These keys also serve as the valid values for rule.theme — design them to cover the \
  psychological range your rules will need.

Call create_saga exactly once.
"""

_TOOL = {
    "name": "create_saga",
    "description": "Output a complete Loombound saga structure.",
    "input_schema": {
        "type": "object",
        "properties": {
            "saga_id": {
                "type": "string",
                "description": "Unique snake_case ID, e.g. 'drowned_district_act1'",
            },
            "title": {"type": "string"},
            "intro": {"type": "string"},
            "initial_core_state": {
                "type": "object",
                "description": "Starting stats. max_health and sanity are fixed at 100; set health=100, max_health=100, sanity=100. Choose money freely (suggest 5–15). depth=1, act=1.",
                "properties": {
                    "health":     {"type": "integer", "const": 100},
                    "max_health": {"type": "integer", "const": 100},
                    "money":      {"type": "integer"},
                    "sanity":     {"type": "integer", "const": 100},
                    "depth":      {"type": "integer", "const": 1},
                    "act":        {"type": "integer", "const": 1},
                },
                "required": ["health", "max_health", "money", "sanity", "depth", "act"],
                "additionalProperties": False,
            },
            "tone": {
                "type": "string",
                "description": (
                    "2–4 sentences describing the saga's genre, atmosphere, and aesthetic. "
                    "Used by the runtime content generator for every waypoint. Be specific."
                ),
            },
            "start_waypoint_id": {
                "type": "string",
                "description": "Must match one of the node_ids you define.",
            },
            "waypoints": {
                "type": "array",
                "minItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "waypoint_id": {
                            "type": "string",
                            "description": "snake_case, unique within saga",
                        },
                        "label":      {"type": "string", "description": "Short display name"},
                        "map_blurb":  {"type": "string", "description": "1–2 atmospheric sentences for map screen"},
                        "waypoint_type":  {"type": "string"},
                        "depth":      {"type": "integer", "minimum": 1},
                        "encounter_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                        },
                        "next_waypoints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "node_ids this node leads to. Empty list = terminal.",
                        },
                    },
                    "required": [
                        "waypoint_id", "label", "map_blurb", "waypoint_type",
                        "depth", "encounter_count", "next_waypoints",
                    ],
                    "additionalProperties": False,
                },
            },
            "toll_lexicon": {
                "type": "array",
                "description": (
                    "3–6 saga-specific toll labels. "
                    "Must include 'stable' and 'destabilizing'. "
                    "Add theme-specific entries (e.g. 'cursed', 'exploitative')."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id":          {"type": "string", "description": "Short snake_case label, e.g. 'cursed'"},
                        "description": {"type": "string", "description": "One-line numeric constraint, e.g. 'net delta clearly negative'"},
                    },
                    "required": ["id", "description"],
                    "additionalProperties": False,
                },
            },
            "rules": {
                "type": "array",
                "description": "3–5 saga-specific rules defining this world's psychological logic.",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "id":                    {"type": "string"},
                        "name":                  {"type": "string"},
                        "theme":                 {"type": "string"},
                        "decision_types":        {"type": "array", "items": {"type": "string"}},
                        "priority":              {"type": "integer"},
                        "sanity_penalty":        {"type": "integer"},
                        "preferred_option_tags": {"type": "array", "items": {"type": "string"}},
                        "forbidden_option_tags": {"type": "array", "items": {"type": "string"}},
                        "match": {
                            "type": "object",
                            "properties": {
                                "required_context_tags": {"type": "array", "items": {"type": "string"}},
                                "max_health":  {"type": "integer"},
                                "min_health":  {"type": "integer"},
                                "max_money":   {"type": "integer"},
                                "min_money":   {"type": "integer"},
                                "max_sanity":  {"type": "integer"},
                                "min_sanity":  {"type": "integer"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "required": ["id", "name", "theme", "decision_types", "priority",
                                 "sanity_penalty", "preferred_option_tags", "forbidden_option_tags"],
                    "additionalProperties": False,
                },
            },
            "narration_table": {
                "type": "object",
                "description": (
                    "10–15 per-saga psychological theme labels. "
                    "Each key is a snake_case theme name; each value is one sentence of inner experience. "
                    "Must include 'neutral'. Rule.theme values must be keys from this table."
                ),
                "additionalProperties": {"type": "string"},
                "minProperties": 10,
            },
        },
        "required": ["saga_id", "title", "intro", "tone", "initial_core_state", "start_waypoint_id", "waypoints", "toll_lexicon", "rules", "narration_table"],
        "additionalProperties": False,
    },
}


def _build_user_msg(
    theme: str,
    node_count: int,
    lang: str,
    tone_hint: str | None = None,
    worldview_hint: str | None = None,
) -> str:
    parts = [
        f"Design a Loombound saga with exactly {node_count} waypoints.",
        f"Theme: {theme}",
    ]
    if tone_hint:
        parts.append(
            "Tone guidance: "
            f"{tone_hint}\nTreat this as a strong creative constraint for genre, mood, imagery, and voice."
        )
    if worldview_hint:
        parts.append(
            "Worldview / setting guidance: "
            f"{worldview_hint}\nUse this as a strong constraint for setting logic, factions, technology or magic assumptions, and recurring motifs."
        )
    parts.append(
        "Use a branching graph structure with at least one fork. "
        "Make sure every waypoint_id in next_waypoints actually exists in your waypoints list. "
        f"The final waypoints list must contain exactly {node_count} unique waypoints."
    )
    if lang == "zh":
        parts.append(
            "Write all narrative text (title, intro, tone, label, map_blurb) in Chinese (中文). "
            "waypoint_id and waypoint_type remain in English snake_case."
        )
    return "\n".join(parts)
