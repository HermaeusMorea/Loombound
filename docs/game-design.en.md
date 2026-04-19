# Loombound Game Design

## Project Overview

A CLI text adventure / tabletop-style roguelite focused on Lovecraftian sanity pressure and narrative arbitration.  
Main entry point: `./loombound run`

---

## Runtime Object Model

Three core objects form the lifecycle of an entire run:

```
Run
└── Waypoint (×N)
    └── Encounter (×1..M)
```

### Run

Host of an entire game session. Holds:
- `CoreState` — numeric state (health / money / sanity / depth / act)
- `MetaState` — narrative interpretation layer (active_marks, major_events, traumas)
- `RunMemory` — long-term cross-waypoint memory
- `RuleSystem` — rule system state for the entire run

### Waypoint

A single location / scene container on the map. Lifecycle:
1. Entered from Run, inherits a state view
2. Processes one or more Encounters sequentially
3. Generates a WaypointSummary on exit; important results written back to RunMemory
4. Waypoint destroyed

Holds: `WaypointMemory`, `WaypointRuleState`

### Encounter

A single event-choice / arbitration unit. Contains:
- `EncounterContext` (scene_type, depth/act, resources, tags, state view)
- options (list of choices, with C2-generated tolls and effects)
- selected option + result
- status

---

## State Layers

### CoreState (structured, deterministic)

- health / money / sanity
- depth / act / location
- inventory tags
- Validated and updated by the kernel; LLM does not write directly

### MetaState (narrative interpretation layer)

- active_marks (persistent state tags, e.g. `lamp_oil`, `warding_tools`)
- metadata.major_events / traumas / narrator_mood
- Text-based state suited for LLM generation and interpretation

---

## Memory Model

### RunMemory (long-term cross-waypoint memory)

Stores: sanity, recent_rules, recent_shocks, behavior_counters, important_incidents, narrator_mood

Used for: providing long-term context to subsequent encounters, supplying lightweight bias to the rule system, providing summaries to LLM generation

### WaypointMemory (short-term in-waypoint memory)

Stores: events, choices_made, shocks_in_waypoint, sanity_lost_in_waypoint, important_flags, waypoint_summary

Used for: describing what happened within a waypoint, distilling important information into RunMemory at waypoint exit

---

## Rule System

Three components:

- **RuleTemplate** — static rule template defining applicable scenes, theme (a key in the per-saga narration_table), match conditions, preferred/forbidden option tags, sanity_penalty
- **RuleSystem** — run-level, holds templates, tracks recent usage and use counts
- **WaypointRuleState** — waypoint-level, current available rules, candidate rules, selected rule, selection trace

Rule selection is sorted by `(-freshness_penalty, priority, id)` — no theme scores.

---

## Deterministic Main Chain

Execution order for each Encounter:

```
context → rule matching → rule selection → enforcement → narration → state update
```

1. RuleTemplate matches against the current encounter (context tags + option tags)
2. RuleSystem + RunMemory lightly rank candidate rules (freshness penalty + priority)
3. Select primary rule
4. Enforcement: apply C2-generated toll, compute sanity_cost/delta
5. Narration: look up a single psychological sentence from the saga's narration_table by `rule.theme` (fallback to `"neutral"`)
6. Write selected option's effects back to Run

---

## State Adapter Layer (`state_adapter`)

The only sanctioned boundary for external content entering the system:
- Reads JSON assets → internal runtime objects
- Receives LLM-generated structured content packages → internal runtime objects
- Guarantees the kernel always processes uniform internal objects, never raw free text

---

## Presentation Layer

CLI ANSI terminal interface:
- Top HUD (numeric state, current waypoint info)
- Middle content area (scene description, encounter results, map)
- Bottom input area

Features:
- Two-column HUD, automatically stacks vertically on narrow terminals
- Fixed input box with prompt before input
- Slow paced segment-by-segment display, buying time for background generation

---

## Data Asset Structure

```
data/
├── sagas/<id>.json                      ← waypoint topology graph (C3/Opus generated)
├── sagas/<id>_toll_lexicon.json         ← per-saga toll vocabulary (C3 generated)
├── sagas/<id>_rules.json                ← per-saga rule set (C3 generated, contains rule.theme keys)
├── sagas/<id>_narration_table.json      ← per-saga narration themes (C3 generated, 10–15 entries)
├── waypoints/<id>/scene_skeletons.json   ← waypoint scene skeletons (C2/Haiku generated)
└── arc_state_catalog.json                  ← global bearing enumeration (C3 one-time)
```

---

## Module Structure

| Directory | Layer | Responsibility |
|---|---|---|
| `src/t0/memory/` | A0 | CoreState, RunMemory, WaypointMemory and other data models |
| `src/t0/core/` | C0 | enforcement, rule_engine, state_adapter, signal_interpretation |
| `src/t1/core/` | C1 | C1 expander (qwen2.5:7b scene text expansion), prompts, ollama transport |
| `src/t2/memory/` | A2 | bearing entries, toll lexicon and other data models (a2_store) |
| `src/t2/core/` | C2 | m2_classifier, prefetch, gen_a1_cache_table, collector |
| `src/t3/core/` | C3 | saga generation logic (generate_campaign, gen_a2_cache_table) |
| `src/runtime/` | assembly | play_cli, session, campaign; the only location allowed to import all layers |
