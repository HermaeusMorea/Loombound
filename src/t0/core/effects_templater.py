"""Deterministic per-option effect generator — replaces M2 LLM effect assignment.

Input: selected rule + option list + current quasi-state bands.
Output: per-option {health_delta, money_delta, sanity_delta, toll}.

Classification bucket:
  - forbidden : option.tags intersects rule.forbidden_option_tags
  - preferred : option.tags intersects rule.preferred_option_tags (and not forbidden)
  - neutral   : otherwise

Each bucket maps to {toll, h[lo,hi], m[lo,hi], s[lo,hi]}. The final integer
for each delta is picked inside the range biased by the matching band:
  band low   → range endpoint closer to hi (more lenient / more generous)
  band high  → range endpoint closer to lo (harsher / stricter)

The rule may carry a saga-specific `effects_template` (produced by Opus at
saga generation). When absent, a conservative default is used so existing
sagas keep running.
"""

from __future__ import annotations

from typing import Any

from src.shared import config
from src.shared import embedder as _embedder
from src.t0.memory import RuleTemplate


# Cosine threshold above which a tag is considered "matching" a bucket.
# Calibrated against paraphrase-multilingual-MiniLM-L12-v2 on Chinese+English
# pairs: related-semantic cosines sit roughly in [0.45, 0.90]; unrelated
# cosines sit in [0.03, 0.22]. 0.35 captures the lowest paraphrase (0.447)
# while rejecting the highest unrelated (0.218). Rerun calibration if you
# change the model.
_TAG_MATCH_THRESHOLD = 0.35


_CLAMPS = {
    "health_delta": (config.HEALTH_DELTA_MIN, config.HEALTH_DELTA_MAX),
    "money_delta":  (config.MONEY_DELTA_MIN,  config.MONEY_DELTA_MAX),
    "sanity_delta": (config.SANITY_DELTA_MIN, config.SANITY_DELTA_MAX),
}


def _clamp(value: int, field: str) -> int:
    lo, hi = _CLAMPS[field]
    return max(lo, min(hi, value))


# Fallback template used when a rule has no `effects_template`.
# Deltas are expressed as FRACTIONS of the saga's own scale so the default
# feels right for any max_health (e.g. 100 or 50 or 20):
#   h_ratio → multiplied by run.core_state.max_health
#   s_ratio → multiplied by sanity_max (fixed 100 — effects.py clamps sanity to 0..100)
#   m_ratio → multiplied by config.MONEY_MAX (the band-normalisation ceiling)
# Final integer is still clamped to config.*_DELTA_MIN/MAX.
_DEFAULT_TEMPLATE_RATIOS: dict[str, dict[str, Any]] = {
    "preferred": {
        "toll": "stable",
        # 0 → +3% recovery / reward
        "h_ratio": (0.00,  0.03),
        "m_ratio": (0.00,  0.07),
        "s_ratio": (0.00,  0.03),
    },
    "forbidden": {
        "toll": "destabilizing",
        # -4% → -12% harm (the "you paid for that choice" range)
        "h_ratio": (-0.12, -0.04),
        "m_ratio": (-0.20, -0.07),
        "s_ratio": (-0.08, -0.02),
    },
    # neutral bucket keeps toll="stable" (enforcement.sanity_penalty stays 0)
    # but carries a non-zero cost so options that miss both preferred and
    # forbidden tag sets still feel like a real choice.
    "neutral": {
        "toll": "stable",
        # -1% → -5% — the world takes its toll from every choice
        "h_ratio": (-0.05, -0.01),
        "m_ratio": (-0.07,  0.00),
        "s_ratio": (-0.03, -0.01),
    },
}

_DEFAULT_SANITY_MAX = 100   # effects.py clamps sanity to [0, 100]
_DEFAULT_HEALTH_MAX = 100   # used if core_state.max_health is missing
_DEFAULT_MONEY_SCALE = config.MONEY_MAX  # 15 — same as band normalisation


def _ratio_range_to_absolute(
    ratio_pair: tuple[float, float] | list[float],
    scale: int,
) -> tuple[int, int]:
    if not ratio_pair or len(ratio_pair) != 2:
        return (0, 0)
    return (round(ratio_pair[0] * scale), round(ratio_pair[1] * scale))

_BAND_POSITION = {
    "very_low":  0.0,
    "low":       0.25,
    "moderate":  0.5,
    "high":      0.75,
    "very_high": 1.0,
    "unknown":   0.5,
}


def _pick(range_pair: list[int] | tuple[int, int], band: str) -> int:
    if not range_pair or len(range_pair) != 2:
        return 0
    lo, hi = int(range_pair[0]), int(range_pair[1])
    if lo > hi:
        lo, hi = hi, lo
    pos = _BAND_POSITION.get(band, 0.5)
    # band low → hi, band high → lo
    return round(hi + (lo - hi) * pos)


def _bucket(option_tags: list[str], rule: RuleTemplate | None) -> str:
    """Classify an option into preferred / forbidden / neutral bucket.

    Two paths:
    - Fast path: string-set intersection (cheap, zero deps).
    - Semantic path: when embedder is available, also check max cosine
      similarity against the rule's pre-embedded tag sets so close paraphrases
      (e.g. "shelter" ≈ "hide") still match.
    """
    if rule is None:
        return "neutral"

    tag_set = {t for t in option_tags if t}
    forbid_tags = set(rule.forbidden_option_tags or [])
    pref_tags = set(rule.preferred_option_tags or [])

    # Fast path — direct string match.
    if tag_set & forbid_tags:
        return "forbidden"
    if tag_set & pref_tags:
        return "preferred"

    # Semantic path — embed option tags and check against pre-computed rule
    # tag embeddings. Requires saga_loader to have attached _forbid_embeddings
    # and _pref_embeddings to the rule; falls back to neutral if not attached.
    if _embedder.is_available() and tag_set:
        forbid_vecs = getattr(rule, "_forbid_embeddings", None)
        pref_vecs = getattr(rule, "_pref_embeddings", None)
        if forbid_vecs or pref_vecs:
            try:
                option_vecs = _embedder.embed_batch(list(tag_set))
            except Exception:
                return "neutral"
            max_forb = max(
                (_embedder.max_cosine_against(v, forbid_vecs or []) for v in option_vecs),
                default=0.0,
            )
            if max_forb >= _TAG_MATCH_THRESHOLD:
                return "forbidden"
            max_pref = max(
                (_embedder.max_cosine_against(v, pref_vecs or []) for v in option_vecs),
                default=0.0,
            )
            if max_pref >= _TAG_MATCH_THRESHOLD:
                return "preferred"

    return "neutral"


def _resolve_bucket_ranges(
    bucket_name: str,
    rule: RuleTemplate | None,
    max_health: int,
    max_sanity: int,
    money_scale: int,
) -> dict[str, Any]:
    """Produce absolute {toll, h, m, s} ranges for one bucket.

    Precedence:
      1. If the rule's `effects_template[bucket]` provides absolute ranges
         (authored by Opus at saga generation), use them as-is.
      2. Otherwise, convert the default ratio bucket using the given scales.
    """
    custom = None
    if rule is not None:
        template = getattr(rule, "effects_template", None)
        if isinstance(template, dict):
            custom = template.get(bucket_name)

    default = _DEFAULT_TEMPLATE_RATIOS[bucket_name]
    toll = default["toll"]
    h_range = _ratio_range_to_absolute(default["h_ratio"], max_health)
    m_range = _ratio_range_to_absolute(default["m_ratio"], money_scale)
    s_range = _ratio_range_to_absolute(default["s_ratio"], max_sanity)

    if isinstance(custom, dict):
        toll = custom.get("toll", toll)
        h_range = tuple(custom["h"]) if isinstance(custom.get("h"), (list, tuple)) else h_range
        m_range = tuple(custom["m"]) if isinstance(custom.get("m"), (list, tuple)) else m_range
        s_range = tuple(custom["s"]) if isinstance(custom.get("s"), (list, tuple)) else s_range

    return {"toll": toll, "h": h_range, "m": m_range, "s": s_range}


def generate_effects(
    rule: RuleTemplate | None,
    options: list[dict],
    bands: dict[str, str],
    *,
    max_health: int = _DEFAULT_HEALTH_MAX,
    max_sanity: int = _DEFAULT_SANITY_MAX,
    money_scale: int = _DEFAULT_MONEY_SCALE,
) -> dict[str, dict[str, Any]]:
    """Produce per-option effects for every option in the encounter.

    Args:
        rule: the selected rule (may be None → all options use neutral bucket)
        options: encounter options; each must have `option_id` and may have `tags`
        bands: {"health": band, "money": band, "sanity": band} — use _band()
        max_health: saga's max_health (defaults to 100); scales default h ratios
        max_sanity: sanity ceiling (defaults to 100, matches effects.py clamp)
        money_scale: scaling basis for money deltas (defaults to config.MONEY_MAX)

    Returns:
        {option_id: {"health_delta": int, "money_delta": int,
                     "sanity_delta": int, "toll": str}}
    """
    h_band = bands.get("health", "moderate")
    m_band = bands.get("money", "moderate")
    s_band = bands.get("sanity", "moderate")

    # Resolve each bucket's absolute ranges once (same for all options in this call)
    bucket_cache: dict[str, dict[str, Any]] = {
        name: _resolve_bucket_ranges(name, rule, max_health, max_sanity, money_scale)
        for name in ("preferred", "forbidden", "neutral")
    }

    out: dict[str, dict[str, Any]] = {}
    for option in options:
        opt_id = option.get("option_id", "")
        if not opt_id:
            continue
        bucket = _bucket(option.get("tags", []), rule)
        spec = bucket_cache[bucket]
        out[opt_id] = {
            "health_delta": _clamp(_pick(spec["h"], h_band), "health_delta"),
            "money_delta":  _clamp(_pick(spec["m"], m_band), "money_delta"),
            "sanity_delta": _clamp(_pick(spec["s"], s_band), "sanity_delta"),
            "toll":         spec.get("toll", "stable"),
        }
    return out
