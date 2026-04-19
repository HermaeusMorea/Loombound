"""Three-tier cached context bundle for M2 classifier calls.

Tier 1 — global_blocks   arc-state catalog        session-stable, shared across sagas
Tier 2 — saga_blocks     scene option index +      per-saga stable, cached on first
                         rules + toll lexicon       encounter and reused all saga
Tier 3 — dynamic_blocks  quasi game state +        per-call, never cached
                         arb hint

Token budget per call (after cache warm-up):
  global_blocks   → user[0]  cache_control: ephemeral  ~1,500 tokens  @ 0.1× rate
  saga_blocks     → user[1]  cache_control: ephemeral  ~2,000 tokens  @ 0.1× rate
  dynamic_blocks  → user[2]  (no cache_control)          ~300 tokens  @ 1.0× rate

This separation is what makes M2 cheap at runtime: only ~300 tokens are billed
at full price per call once both cache tiers are warm.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CachedContextBundle:
    """Structured three-tier context ready for an M2 classifier call."""

    global_blocks: list[dict]
    saga_blocks: list[dict]
    dynamic_blocks: list[dict]

    def to_user_content(self) -> list[dict]:
        """Flatten all tiers into a single Anthropic user-message content list."""
        return self.global_blocks + self.saga_blocks + self.dynamic_blocks


def build_m2_context(
    *,
    arc_state_catalog_json: str,
    scene_option_index_json: str = "",
    rules_json: str = "",
    toll_lexicon_json: str = "",
    quasi_state: str,
    arb_hint: str = "",
) -> CachedContextBundle:
    """Build a CachedContextBundle for one M2 classifier call.

    Args:
        arc_state_catalog_json:  Serialized arc-state catalog (global tier).
        scene_option_index_json: Serialized scene option index (saga tier).
        rules_json:              Saga rule list JSON (appended to saga tier).
        toll_lexicon_json:       Saga toll lexicon JSON (appended to saga tier).
        quasi_state:             Current game state description (dynamic tier).
        arb_hint:                Next-encounter targeting hint (dynamic tier).
    """
    global_blocks: list[dict] = [
        {
            "type": "text",
            "text": f"Arc-state catalog:\n{arc_state_catalog_json}",
            "cache_control": {"type": "ephemeral"},
        }
    ]

    saga_blocks: list[dict] = []
    if scene_option_index_json:
        rules_suffix = (
            f"\n\nSaga rules (select one per encounter):\n{rules_json}"
            if rules_json else ""
        )
        toll_suffix = (
            f"\n\nToll lexicon for this saga:\n{toll_lexicon_json}"
            if toll_lexicon_json else ""
        )
        saga_blocks.append({
            "type": "text",
            "text": (
                "Scene option index (waypoint option structure for this saga, no effect values):\n"
                f"{scene_option_index_json}{rules_suffix}{toll_suffix}"
            ),
            "cache_control": {"type": "ephemeral"},
        })

    dynamic_blocks: list[dict] = [
        {"type": "text", "text": quasi_state + arb_hint}
    ]

    return CachedContextBundle(
        global_blocks=global_blocks,
        saga_blocks=saga_blocks,
        dynamic_blocks=dynamic_blocks,
    )
