# Loombound Architecture

---

## System Main Path

```
arc-palette (one-time)
  C3 (Opus) → arc-state catalog (~50 bearing entries)

gen (per saga)
  C3 (Opus) → saga.json (waypoint graph + toll lexicon + rules + narration_table)
  C2 (Haiku) → scene_skeletons.json (per-waypoint scene skeletons)

run (game session)
  Startup: load arc-state catalog + scene skeletons → build C2 classifier
  Per waypoint:
    PrefetchCache → C1 (qwen2.5:7b) prefetch scene text
    Player makes choice → C2 (Haiku) fire-and-forget →
      entry_id (bearing update) +
      per-option effects + tolls for the next encounter
  Per encounter:
    enforce_rule (C2 toll → sanity penalty)
    apply_option_effects (update A0 state)
    PrefetchCache consumes effects + tolls

report
  Parse logs/llm.md → token usage + 1000-play cost comparison report
```

---

## Data Flow

```
Offline                                Runtime
──────────────────────────────────     ──────────────────────────────────────

C3 (Opus)
 └─ saga.json                          load saga.json
    waypoints / tone / toll lexicon ──→  RunSession
    rules + narration_table         ──→  RuleSystem
 └─ arc_state_catalog.json            ──→  C2 classifier (global cached prefix)

C2 (Haiku, offline)
 └─ scene_skeletons.json            ──→  C2 classifier (per-saga cached prefix)
                                        + A1 option index (derived, not stored)

                                    Player selects encounter N
                                       │
                                    C2 (Haiku) ←── tendency (A0 compressed)
                                       │             arc-state catalog (cached)
                                       │             A1 option index (cached)
                                       │             toll lexicon (cached)
                                       ▼
                                    entry_id + effects + tolls (encounter N+1)
                                       │
                                    PrefetchCache (in-memory)
                                       │
                                    consumed when encounter N+1 renders
                                       │
                                    enforce_rule → OptionResult (toll + sanity_cost)
                                    apply_option_effects → A0 state update
                                       │
                                    narration_table.get(rule.theme) → one-sentence psychological note
```

---

## Directory Structure and Module Dependencies

Rule: **lower layers do not import higher layers**. `runtime/` is the sole assembly point allowed to import all layers.

```
src/
  runtime/         ← assembly point, imports all layers
    play_cli.py          ← CLI main loop (_play_node, main)
    play_encounter.py    ← encounter execution layer (_play_encounter, _overlay_effects)
    session.py
    saga.py

  t3/              ← C3 (Opus) + A3 data structures
    core/
      generate_saga.py     ← saga generation orchestration
      saga_prompt.py       ← tool schema, _build_user_msg, cost helpers
      saga_validate.py     ← graph validation (validate_graph, _normalise)
      saga_write.py        ← file writing (write_saga, print_graph)
      gen_a2_cache_table.py  ← arc-state catalog generation

  t2/              ← C2 (Haiku) + A2 data structures
    core/
      m2_classifier.py       ← runtime bearing classifier
      prefetch.py            ← background prefetch + bearing state tracking
      gen_a1_cache_table.py  ← scene skeletons generation (per-saga)
      collector.py           ← tendency state construction
      types.py               ← EncounterSeed / PrefetchEntry
    memory/
      a2_store.py            ← arc-state catalog / scene skeletons / A1 option index loader (includes ArcStateEntry, A1Entry, A1Store, RuntimeTableStore)

  t1/              ← C1 (qwen2.5:7b) + A1 data structures
    core/
      expander.py            ← C1 scene text expansion
      prompts.py             ← C1 prompt construction
      ollama.py              ← ollama /api/chat transport
    memory/
      a1_store.py            ← A1Entry data model

  t0/              ← C0 (deterministic) + A0 data structures
    core/
      enforcement.py         ← toll → sanity_cost calculation
      rule_matcher.py        ← RuleTemplate matching
      rule_selector.py       ← candidate rule ranking (freshness penalty + priority)
      rule_state.py          ← runtime rule system state (Run / Waypoint level)
      context_builder.py     ← EncounterContext construction
      signals.py             ← deterministic signal extraction from encounter input
      effects.py             ← option effects application (health / money / sanity delta)
      cli.py                 ← terminal rendering (HUD, options, narration)
    memory/
      models.py              ← CoreState, EncounterContext, OptionResult and other core models
      types.py               ← WaypointMemory, NodeChoiceRecord, etc.
      encounter.py           ← Encounter data structure and lifecycle
      run_memory.py          ← RunMemory operations
      recording.py           ← choice record write-back
```

**Forbidden import directions:**
- `t0/` must not import `t1/`, `t2/`, `t3/`
- `t1/` must not import `t2/`, `t3/`
- `t2/` must not import `t3/`
- No layer may import `runtime/`

---

## Information Flow Direction

| Direction | Description | Implementation |
|---|---|---|
| **Top-down** | Higher-layer core output serves as constraint seed for lower layers | C3 saga → C2 scene skeleton → C1 expansion |
| **Bottom-up** | Lower-layer precise state compressed into higher-layer language | A0 exact values → tendency → C2 (Haiku) |

C2 never touches exact integers — only tendency bands (low/moderate/high) and narrative dimension descriptions.

---

## Key Invariants

1. **Toll is output by C2 at runtime** — scene skeleton stores no tolls (static annotations cannot sense player state)
2. **C2 outputs toll before effect values** (enforced by schema field order) — values must be consistent with toll
3. **C2 format validation failure triggers retry** (up to 2 times) — no fallback to deterministic rules
4. **PrefetchCache is the sole cross-encounter state transfer channel** (effects + tolls held in memory, never written to disk)
5. **narration_table is generated by C3 per saga** (10–15 entries, one psychological sentence each) — rule.theme must be a key in this table
6. **Rule selection uses no theme scoring** — ranked solely by `(-freshness_penalty, priority, id)`
