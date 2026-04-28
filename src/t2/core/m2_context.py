"""Two-tier cached context bundle for M2 arc-state classifier calls.

Tier 1 — global_blocks   arc-state catalog          session-stable, shared across sagas
Tier 2 — dynamic_blocks  quasi game state + hint    per-call, never cached

Rule selection and effect assignment no longer live in M2 — they are handled
downstream by the symbolic rule_selector and effects_templater. The old saga
tier (option index + rules + toll lexicon) has been removed; M2 only needs the
arc catalog to classify.

Token budget per call (after cache warm-up):
  global_blocks   → user[0]  cache_control: ephemeral  ~1,500 tokens  @ 0.1× rate
  dynamic_blocks  → user[1]  (no cache_control)          ~300 tokens  @ 1.0× rate
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CachedContextBundle:
    """Structured context ready for an M2 classifier call."""

    global_blocks: list[dict]
    dynamic_blocks: list[dict]
    # saga_blocks retained as an empty list for backward compat with earlier
    # tests / callers; no longer populated.
    saga_blocks: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.saga_blocks is None:
            self.saga_blocks = []

    def to_user_content(self) -> list[dict]:
        """Flatten all tiers into a single Anthropic user-message content list."""
        return self.global_blocks + self.saga_blocks + self.dynamic_blocks


def build_m2_context(
    *,
    arc_state_catalog_json: str,
    scene_option_index_json: str = "",   # accepted for back-compat; unused
    rules_json: str = "",                # accepted for back-compat; unused
    toll_lexicon_json: str = "",         # accepted for back-compat; unused
    quasi_state: str,
    arb_hint: str = "",
) -> CachedContextBundle:
    """Build a CachedContextBundle for one M2 arc classifier call.

    The M2 classifier now operates on arc catalog + quasi state alone. Saga-
    specific context (rules, option index, toll lexicon) is intentionally
    excluded: rule selection is symbolic, effects are templater-generated.
    """
    global_blocks: list[dict] = [
        {
            "type": "text",
            "text": f"Arc-state catalog:\n{arc_state_catalog_json}",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    dynamic_blocks: list[dict] = [
        {"type": "text", "text": quasi_state + arb_hint}
    ]

    return CachedContextBundle(
        global_blocks=global_blocks,
        dynamic_blocks=dynamic_blocks,
    )
