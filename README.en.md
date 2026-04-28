# Loombound

> Project Status
> This repository contains the previous runnable prototype of Loombound (V1).
> It can still be run and still reflects the core design ideas of the project.
> However, the new architecture currently being planned will shift toward an Opus -> Haiku -> GPT-5.4-nano -> cloud-based qwen2.5 -> local CPU pipeline.
> The new architecture will further reduce token costs. The M2DecisionEngine, which was originally installed on Haiku, will be moved to a smaller model such as GPT-5.4-nano.
> Text expansion will be handled by qwen2.5 in the cloud, which should significantly improve runtime speed.
> Therefore, please treat this repository as a stable reference version rather than the implementation of the latest architecture.

> Chinese Version: [README.md](README.md)

A roguelite narrative engine driven by a three-layer AI architecture.

## This Is Not Another AI App

**Making AI the semantic computation core inside the system, rather than a question-answering interface bolted on from the outside.**

`Loombound` is not the final product. It is a runnable vertical demo built to test one question: if a program needs to continuously process states like "meaning", "tendency", "narrative pressure", and "consequence semantics" that traditional software struggles to represent natively, how should the system be structured?

**Good layered design can dramatically reduce cost and improve runtime speed.** -> [Cost Efficiency](#cost-efficiency) · [Runtime Speed](#runtime-speed)

The reason for choosing a narrative game as the demo is not that the end goal is merely to build games. It is that text games are unusually good at exposing the genuinely hard problems in a semantic system.

-> If you only have time to read one document, start with [LANGUAGE.en.md](docs/LANGUAGE.en.md).

`LANGUAGE.en.md` is not a terminology appendix. It is the conceptual entry point of this project.
It defines how Loombound describes semantic layers, processing cores, runtime objects, and how those things flow through the system.

-> Full write-up: [docs/SEMANTIC_OS.en.md](docs/SEMANTIC_OS.en.md)


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

After setup you can use either `./loombound` or `loombound` directly (with the venv activated: `source .venv/bin/activate`).

---

## Quick Start

```bash
# Prerequisites: ANTHROPIC_API_KEY in .env, ollama running, and qwen2.5:7b pulled
cp .env.example .env   # fill in ANTHROPIC_API_KEY

# 1. One-time global setup (skip if data/arc_state_catalog.json already exists)
./loombound arc-palette

# 2. Generate a saga (Opus builds the graph, Haiku generates scene skeletons automatically)
./loombound gen "Singapore underground hacker community" --lang zh
./loombound gen "solar sail era archaeological investigation" --tone "melancholic, poetic, space mystery with a faint sense of hope" --lang zh
./loombound gen "debt hunter escape" --worldview "Jupiter orbital colonies jointly ruled by the Debt Guild and the Salvage Church" --lang zh

# 3. Launch the game (preloaded path: Haiku bearing classification + local qwen2.5:7b expansion)
# --lang zh generates Chinese scene text; omit it for English
./loombound run --lang zh   # Chinese
./loombound run             # English

# Specify a saga
./loombound run --saga hunters_night_yharnam_last_lucid --lang zh

# Limit waypoint count for testing
./loombound run --nodes 2 --lang zh
```

---

## Three-Layer Architecture

| Phase | AI | Role |
|---|---|---|
| **One-time** | Claude Opus (C3) | Generate the global bearing enumeration (`arc-palette`, ~50 entries) |
| **Per saga** | Claude Opus (C3) | Generate the saga graph (waypoint topology, toll lexicon, rules, narration_table) |
| **Per saga** | Claude Haiku (C2) | Generate scene skeletons (per-waypoint scene skeletons: `scene_concept`, option structure, no numeric values) |
| **Runtime** | Claude Haiku (C2) | Bearing classifier: after each choice, run in the background -> bearing ID + per-option effects and tolls for the next encounter (about `$0.0013` per call after prompt-cache hits) |
| **Runtime** | Local qwen2.5:7b (C1) | Scene expansion: scene skeleton + bearing tendency -> full scene prose |

The full system only requires `ANTHROPIC_API_KEY` plus ollama (local qwen2.5:7b).

Opus appears only in offline phases (`arc-palette` and saga generation). Runtime is entirely Haiku + qwen2.5:7b.

### Cost Efficiency

The core benefit of the three-layer architecture is **turning high-frequency runtime scene expansion from API usage into local compute**.

| Strategy | Offline x1 | Per run | 1000-run total |
|---|---|---|---|
| **tiered (current)** Opus gen + Haiku C2 + local C1 | $0.1129 | $0.0148 | **$14.88** |
| all Opus (both C2 + C1 replaced by Opus) | $0.2450 | $0.2199 | $220.11 |
| all Haiku (saga generation also moved to Haiku) | $0.0392 | $0.0352 | $35.22 |

Measured data: `deep_mine_cult_act1` (4 waypoints, 8 choices). C2 costs about `$0.0019` per choice after Haiku `cache_read` hits. Offline cost gets amortized as play volume grows.

`./loombound report` outputs a live cost report including a 1000-run projection.

-> Full breakdown: [docs/llm-architecture.en.md](docs/llm-architecture.en.md#cost-analysis)

### Runtime Speed

With the prompt-cache "table lookup" pattern, the ideal latency for each stage is:

| Phase | Trigger | Model | Ideal latency |
|---|---|---|---|
| **arc-palette** | One-time | Claude Opus (C3) | 30-90 s |
| **Saga generation** | Per saga | Claude Opus + Haiku (C3 + C2) | 1-3 min |
| **Bearing classification** | Per choice (background) | Claude Haiku (C2, prompt-cache hit) | **1-2 s** |
| **Scene expansion** | Per encounter (background prefetch) | Local qwen2.5:7b (C1) | **2-10 s** (with GPU) |

The 1-2 seconds for C2 is mostly network round-trip plus very short output (roughly 10-30 tokens for the bearing ID). After a prompt-cache hit, latency no longer grows with cache table size. With a suitable GPU, C1 and C2 are in the same rough latency range, and both run in the background, so the player usually does not wait on them.

**C1 local speed depends on hardware.** Loading qwen2.5:7b at full precision takes roughly 4-5 GB of VRAM:

| Environment | Speed | Approx. time per scene |
|---|---|---|
| GPU (RTX 3060 / 4060 class) | 20-50 token/s | ~4-10 s |
| GPU (RTX 4090 / A100 class) | 60-100 token/s | ~2-3 s |
| CPU fallback (no GPU or insufficient VRAM) | 2-8 token/s | 16-37 s |

The author's local GPU is not strong enough, so measured C1 scene expansion falls in the 16-37 second range due to CPU fallback; the latency figures in the logs reflect that condition. With a GPU capable of comfortably holding a 7b model in VRAM, C1 should drop to around 2-10 seconds.

**The bottleneck in saga generation is Haiku, not Opus.** Back-calculating from output token counts: Opus generates the saga graph at about 1,170 tokens (~40 seconds), while Haiku generates scene skeletons at about 6,275 tokens (~63 seconds). Each waypoint needs full `scene_concept`, `sanity_axis`, and option structure output, so across 6 waypoints Haiku ends up producing about 5x the output volume of Opus. Using Haiku instead of a faster model is a deliberate cost tradeoff: Haiku output pricing is roughly 1/19 of Opus, and saga generation can run in the background while play has already started. A full saga usually takes several minutes to finish, so generation completes well before it becomes blocking.

### Data Files

| File | Source | Contents |
|---|---|---|
| `data/arc_state_catalog.json` | Claude Opus (one-time) | Bearing enumeration (~50 entries, loaded into Haiku prompt cache at runtime) |
| `data/sagas/<id>.json` | Claude Opus (per saga) | Saga graph: waypoint topology + per-waypoint `depth` / `type` / `encounters` (inlined) |
| `data/sagas/<id>_toll_lexicon.json` | Claude Opus (per saga) | Per-saga toll lexicon, used as a C2 runtime cached prefix |
| `data/sagas/<id>_rules.json` | Claude Opus (per saga) | Per-saga rule set, including `rule.theme` keys |
| `data/sagas/<id>_narration_table.json` | Claude Opus (per saga) | Per-saga narration theme table (10-15 entries, each a single psychological sentence) |
| `data/waypoints/<id>/scene_skeletons.json` | Claude Haiku (per saga) | Scene skeletons: `scene_concept`, `sanity_axis`, option structure (no `h/m/s` values) |

> The A1 option index (option structure with numeric values removed, used as Haiku's per-saga cached prefix) is derived from scene skeletons at runtime and is not stored as a separate file.

---

## `./loombound` Reference

```bash
./loombound arc-palette                    # Generate the global bearing enumeration (one-time)
./loombound clean-palette                  # Delete the bearing enumeration

./loombound gen "theme" --lang zh          # Default: Opus graph generation + Haiku scene skeleton generation
./loombound gen "theme" --skip-t1-cache    # Generate only the saga graph
./loombound gen "theme" --nodes 8          # Waypoint count (default: 6)
./loombound gen "theme" --tone "..."       # Set tone
./loombound gen "theme" --worldview "..."  # Set worldview

./loombound run                            # Launch the game (auto-selects the latest saga)
./loombound run --lang zh                  # Chinese content
./loombound run --saga ID                  # Specify a saga
./loombound run --nodes 3                  # Limit waypoint count (for testing)
./loombound run --fast MODEL               # Set the local C1 model (default: qwen2.5:7b)

./loombound report                         # Latest token/cost report (includes 1000-run projection)
./loombound report --saga ID

./loombound clean --saga ID                # Delete one saga's data
./loombound clean --all                    # Delete all saga data (keeps the bearing enumeration)
./loombound clean-logs                     # Clear logs/llm.md
```

---

## Prerequisites

```bash
cp .env.example .env   # fill in the required API keys
```

- `ANTHROPIC_API_KEY` — required for both `gen` and `run`
- ollama running (`ollama serve`) with `ollama pull qwen2.5:7b` already downloaded — required for `run` (local C1 expansion)

> **Claude API is required throughout.** `gen` uses Claude Opus (C3) to generate the saga graph, and the C2 classifier used in `run` relies on Anthropic prompt caching. Both require `ANTHROPIC_API_KEY`.

---

## Logs and Reports

LLM calls are recorded in `logs/llm.md`, including token counts, cost, and cache-hit details for each call.

```bash
./loombound report              # Latest run (includes offline cost attribution + 1000-run projection)
./loombound report --saga ID
```

---

The LLM layered architecture used in this game (C0/C1/C2/C3 processing cores and A0-A3 semantic data layers) is informed by another ongoing project by the author.

## License

MIT
