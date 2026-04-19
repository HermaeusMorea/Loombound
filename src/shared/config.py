"""Centralised constants for LLM models, operational params, and game mechanics."""

# ── LLM models ───────────────────────────────────────────────────────────────
M2_MODEL = "claude-haiku-4-5-20251001"
C3_MODEL = "claude-opus-4-6"

# ── M2 classifier ─────────────────────────────────────────────────────────────
M2_MAX_TOKENS  = 220    # entry_id + selected_rule_id + per-option toll + h/m/s
M2_TIMEOUT     = 30.0
M2_MAX_RETRIES = 2

# ── Effect delta clamp bounds (enforced in tool schema AND parse_effects) ─────
HEALTH_DELTA_MIN, HEALTH_DELTA_MAX = -15, 10
MONEY_DELTA_MIN,  MONEY_DELTA_MAX  = -15, 15
SANITY_DELTA_MIN, SANITY_DELTA_MAX = -10, 5

# ── Collector: band thresholds ────────────────────────────────────────────────
BAND_THRESHOLDS = (0.2, 0.4, 0.6, 0.8)   # ratio cutoffs → very_low/low/moderate/high/very_high
MONEY_MAX = 15                             # normalisation ceiling for money band

# ── Collector: trajectory thresholds ──────────────────────────────────────────
SANITY_CRITICAL_THRESHOLD  = 3
SANITY_DEPLETING_THRESHOLD = 2
MOOD_SEVERITY_HIGH         = 4
MOOD_LENIENCY_LOW          = 2

# ── Collector: context window sizes ───────────────────────────────────────────
THEME_TOP_N        = 3
INCIDENT_HISTORY_N = 3
SHOCK_HISTORY_N    = 3
WAYPOINT_HISTORY_N = 4
CHOICE_HISTORY_N   = 2
A1_ENTRY_N         = 3

# ── A1 cache generation ───────────────────────────────────────────────────────
T1_CACHE_BATCH_SIZE = 3
