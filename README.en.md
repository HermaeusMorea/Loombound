# Loombound

> 中文版文档：[README.md](README.md)

A roguelite narrative engine driven by a three-layer AI architecture.

## This Is Not Another AI App

**Making AI the semantic computation core inside the system — not a question-answering interface bolted on from outside.**

`Loombound` is not the end product. It is a runnable vertical demo built to answer one question: if a program needs to continuously handle states like "meaning", "tendency", "narrative pressure", and "consequence semantics" that traditional software cannot natively express, how should the system be structured?

**Good layered design can dramatically reduce cost and improve runtime speed.** → [Cost Efficiency](#cost-efficiency) · [Runtime Speed](#runtime-speed)

The choice of a narrative game as the demo vehicle is not because the goal is to make games — it is because text games are unusually good at exposing the genuinely hard problems of a semantic system.

→ If you only have time to read one document, start with [LANGUAGE.en.md](docs/LANGUAGE.en.md).

`LANGUAGE.en.md` is not a terminology appendix — it is the conceptual entry point for this project.
It defines how Loombound describes semantic layers, processing cores, runtime objects, and how these things flow through the system.

→ Full writeup: [docs/SEMANTIC_OS.en.md](docs/SEMANTIC_OS.en.md)


## Installation

```bash
git clone https://github.com/HermaeusMorea/Loombound.git
cd Loombound

# Create a virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install -e .

# Configure API key
cp .env.example .env   # fill in ANTHROPIC_API_KEY

# Download the local model (used by C1 for scene expansion)
ollama pull qwen2.5:7b
```

After installation you can use either `./loombound` or `loombound` (with the venv activated: `source .venv/bin/activate`).

---

## Quick Start

```bash
# Prerequisites: ANTHROPIC_API_KEY in .env + ollama running: ollama pull qwen2.5:7b
cp .env.example .env   # fill in ANTHROPIC_API_KEY

# 1. One-time global setup — generate the bearing enumeration (skip if data/arc_state_catalog.json exists)
./loombound arc-palette

# 2. Generate a saga (Opus builds the graph, Haiku generates scene skeleton automatically)
./loombound gen "Singapore underground hacker community" --lang zh
./loombound gen "Solar sail era archaeology" --tone "melancholic, poetic, space mystery with a hint of hope" --lang zh
./loombound gen "Debt hunter escape" --worldview "Jupiter orbital colonies ruled jointly by the Debt Guild and the Salvage Church" --lang zh

# 3. Play (preloaded path: Haiku bearing classification + qwen2.5:7b local text expansion)
# --lang zh generates Chinese scene text; omit for English
./loombound run --lang zh   # Chinese
./loombound run             # English

# Specify a saga
./loombound run --saga hunters_night_yharnam_last_lucid --lang zh

# Limit waypoints for testing
./loombound run --nodes 2 --lang zh
```

---

## Three-Layer Architecture

| Phase | AI | Role |
|---|---|---|
| **One-time** | Claude Opus (C3) | Generate global bearing enumeration (`arc-palette`, ~50 entries) |
| **Per saga** | Claude Opus (C3) | Generate saga graph (waypoint topology, toll lexicon, rules, narration_table) |
| **Per saga** | Claude Haiku (C2) | Generate scene skeletons (per-waypoint scene skeletons: scene_concept, option structure, no numeric values) |
| **Runtime** | Claude Haiku (C2) | Bearing classifier: after each player choice → bearing ID + per-option effects + tolls for the next encounter (~$0.0013/call after cache hit) |
| **Runtime** | qwen2.5:7b local (C1) | Scene expander: scene skeleton + bearing tendency → full scene prose |

Only `ANTHROPIC_API_KEY` + ollama (local qwen2.5:7b) required.

Opus only appears in offline phases (arc-palette and saga generation). Runtime is entirely Haiku + qwen2.5:7b.

### Cost Efficiency

The core benefit of the three-layer design is **moving high-frequency runtime scene expansion off the API and onto local compute**.

| Strategy | Offline ×1 | Per play | ×1000 total |
|---|---|---|---|
| **tiered (current)** Opus gen + Haiku C2 + local C1 | $0.1129 | $0.0148 | **$14.88** |
| all-opus (C2 + C1 both Opus) | $0.2450 | $0.2199 | $220.11 |
| all-haiku (saga gen also Haiku) | $0.0392 | $0.0352 | $35.22 |

Measured data: deep_mine_cult_act1 (4 waypoints, 8 choices). C2 costs ~$0.0019 per choice after Haiku cache_read hit. Offline cost is amortized as play volume grows.

`./loombound report` outputs a live cost breakdown including a 1000-play projection.

→ Full cost breakdown: [docs/llm-architecture.en.md](docs/llm-architecture.en.md#cost-analysis)

### Runtime Speed

Ideal latency for each phase using the prompt-cache table-lookup pattern:

| Phase | When | Model | Ideal latency |
|---|---|---|---|
| **arc-palette** | One-time | Claude Opus (C3) | 30–90 seconds |
| **Saga generation** | Per saga | Claude Opus + Haiku (C3 + C2) | 1–3 minutes |
| **Bearing classification** | Per choice (background) | Claude Haiku (C2, prompt cache hit) | **1–2 seconds** |
| **Scene expansion** | Per encounter (background prefetch) | qwen2.5:7b local (C1) | **2–10 seconds** (with GPU) |

C2's 1–2 seconds is dominated by network round-trip plus very short output (~10–30 tokens for the bearing ID). After a prompt cache hit, cached table size has no effect on latency. With a capable GPU, C1 and C2 operate in the same latency range; both run in the background, so players rarely wait on them.

**C1 local speed depends entirely on hardware.** qwen2.5:7b requires ~4–5 GB VRAM to load at full precision:

| Environment | Speed | Time per scene |
|---|---|---|
| GPU (RTX 3060 / 4060 tier) | 20–50 token/s | ~4–10 seconds |
| GPU (RTX 4090 / A100 tier) | 60–100 token/s | ~2–3 seconds |
| CPU fallback (no GPU or insufficient VRAM) | 2–8 token/s | 16–37 seconds |

The author's local GPU is not up to the task — measured C1 latency falls in the 16–37 second range due to CPU inference fallback. The latency figures in the logs reflect this condition. With a card that can hold a 7b model in VRAM, C1 drops to 2–10 seconds.

**The bottleneck in saga generation is Haiku, not Opus.** Back-calculating from output token counts: Opus generates the saga graph in ~1,170 tokens (~40 seconds); Haiku generates the scene skeletons in ~6,275 tokens (~63 seconds) — every waypoint requires a full scene_concept, sanity_axis, and option structure, so 6 waypoints accumulate ~5× the output volume of Opus. Using Haiku instead of a faster model is a deliberate cost decision: Haiku's output rate is roughly 1/19th of Opus's, and saga generation can run in the background while play has already started — a full saga takes several minutes to play through, so generation finishes well before it's needed.

### Data Files

| File | Source | Contents |
|---|---|---|
| `data/arc_state_catalog.json` | Claude Opus (one-time) | Bearing enumeration (~50 entries, Haiku prompt cache at runtime) |
| `data/sagas/<id>.json` | Claude Opus (per saga) | Saga graph: waypoint topology + per-waypoint depth / type / encounters (inlined) |
| `data/sagas/<id>_toll_lexicon.json` | Claude Opus (per saga) | Per-saga toll vocabulary, C2 runtime cached prefix |
| `data/sagas/<id>_rules.json` | Claude Opus (per saga) | Per-saga rule set, contains rule.theme keys |
| `data/sagas/<id>_narration_table.json` | Claude Opus (per saga) | Per-saga narration themes (10–15 entries, single psychological sentence each) |
| `data/waypoints/<id>/scene_skeletons.json` | Claude Haiku (per saga) | Scene skeletons: scene_concept, sanity_axis, option structure (no h/m/s values) |

> A1 option index (option structure without values — Haiku's per-saga cached prefix) is derived from the scene skeletons at runtime and is not stored as a separate file.

---

## `./loombound` Reference

```bash
./loombound arc-palette                    # Generate global bearing enumeration (one-time)
./loombound clean-palette                  # Delete bearing enumeration

./loombound gen "theme" --lang zh          # Default: Opus saga graph + Haiku scene skeleton
./loombound gen "theme" --skip-t1-cache    # Graph only, skip scene skeleton generation
./loombound gen "theme" --nodes 8          # Waypoint count (default: 6)
./loombound gen "theme" --tone "..."       # Set atmospheric tone
./loombound gen "theme" --worldview "..."  # Set worldview / setting

./loombound run                            # Launch game (auto-selects most recent saga)
./loombound run --lang zh                  # Chinese content
./loombound run --saga ID                  # Specify a saga
./loombound run --nodes 3                  # Limit waypoint count (for testing)
./loombound run --fast MODEL               # Specify C1 local model (default: qwen2.5:7b)

./loombound report                         # Token usage / cost for latest run (with 1000-play projection)
./loombound report --saga ID

./loombound clean --saga ID                # Remove a single saga's data
./loombound clean --all                    # Remove all sagas (keeps bearing enumeration)
./loombound clean-logs                     # Truncate logs/llm.md
```

---

## Prerequisites

```bash
cp .env.example .env   # fill in your API keys
```

- `ANTHROPIC_API_KEY` — required for both `gen` and `run`
- ollama running (`ollama serve`) with `ollama pull qwen2.5:7b` — required for `run` (C1 local expansion)

> **Claude API required throughout.** `gen` uses Claude Opus (C3) to generate the saga graph; `run` uses Anthropic prompt caching for the C2 classifier. Both require `ANTHROPIC_API_KEY`.

---

## Logs and Reports

All LLM calls are recorded in `logs/llm.md` with token counts, cost, and cache hit details.

```bash
./loombound report              # Latest run (with offline cost attribution + 1000-play projection)
./loombound report --saga ID
```

---

The LLM layered architecture used in this game (C0/C1/C2/C3 processing cores, A0–A3 data semantic layers) is inspired by a separate ongoing project by the author.
