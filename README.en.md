# Loombound

A roguelite narrative engine driven by a three-layer AI architecture.

> 中文版文档：[README.md](README.md) · [docs/game-design.md](docs/game-design.md) · [docs/llm-architecture.md](docs/llm-architecture.md)

## Quick Start

```bash
# Prerequisites: ANTHROPIC_API_KEY in .env + ollama running: ollama pull gemma3:4b
cp .env.example .env   # fill in ANTHROPIC_API_KEY

# 1. One-time global setup — generate the arc-state palette (skip if data/m2_table_a.json already exists)
./loombound arc-palette

# 2. Generate a campaign (Opus builds the graph, Haiku generates Table B automatically)
./loombound gen "Singapore underground hacker community" --lang zh
./loombound gen "Solar sail era archaeology" --tone "melancholic, poetic, space mystery with a hint of hope" --lang zh
./loombound gen "Debt hunter escape" --worldview "Jupiter orbital colonies ruled jointly by the Debt Guild and the Salvage Church" --lang zh

# 3. Play (preloaded path: Haiku arc classification + gemma3 local text expansion)
# --lang zh generates Chinese scene text; omit for English (default)
./loombound run             # English
./loombound run --lang zh   # Chinese

# Specify a campaign
./loombound run --campaign hunters_night_yharnam_last_lucid --lang zh

# Limit nodes for testing
./loombound run --nodes 2 --lang zh
```

---

## Three-Layer Architecture

| Phase | AI | Role |
|---|---|---|
| **One-time** | Claude Opus | Generate global arc-state palette (`arc-palette`, ~50 enum entries) |
| **Per campaign** | Claude Opus | Generate campaign graph (node topology, labels, map_blurb) |
| **Per campaign** | Claude Haiku | Generate Table B (per-node scene skeletons: scene_concept, option structure, no numeric values) |
| **Runtime** | Claude Haiku | M2 classifier: after each player choice → arc state ID + per-option effects for the next arbitration (~$0.001/call after cache hit) |
| **Runtime** | gemma3:4b (local) | Fast Core: Table B skeleton + arc state tendency → full scene text |

Only `ANTHROPIC_API_KEY` + ollama (local gemma3) required.

Opus only appears in offline phases (arc-palette and campaign generation). Runtime is entirely Haiku + gemma3.

### Cost Efficiency

The core benefit of the three-layer design is **moving high-frequency runtime scene expansion off the API and onto local compute**.

| Approach | Runtime cost per play | 100-play total |
|---|---|---|
| Current (Haiku M2 + local Fast Core) | ~$0.010 | ~$1.1 |
| Opus-only (replace Fast Core) | ~$0.20 | ~$20 |
| **Gap** | | **~18×** |

M2 cost estimate: ~$0.001 per arbitration choice after Haiku prompt cache hit. A typical 5-node, 10-choice run ≈ $0.010. As player count grows, offline cost is amortized and the gap widens further.

→ Full cost breakdown: [docs/llm-architecture.en.md](docs/llm-architecture.en.md#cost-analysis)

### Data Files

| File | Source | Contents |
|---|---|---|
| `data/m2_table_a.json` | Claude Opus (one-time) | Arc-state palette (~50 enum entries, Haiku prompt cache at runtime) |
| `data/campaigns/<id>.json` | Claude Opus (per campaign) | Campaign graph: node topology + per-node floor / type / arbitrations (inlined) |
| `data/nodes/<id>/table_b.json` | Claude Haiku (per campaign) | Scene skeletons: scene_concept, sanity_axis, option structure (no h/m/s values) |

> Table C (option structure without values — Haiku's per-campaign cached prefix) is derived from Table B at runtime and is not stored as a separate file.

---

## `./loombound` Reference

```bash
./loombound arc-palette                    # Generate global arc-state palette (one-time)
./loombound clean-palette                  # Delete arc palette

./loombound gen "theme"                    # Default: Opus graph + Haiku Table B
./loombound gen "theme" --lang zh          # Generate content in Chinese
./loombound gen "theme" --skip-table-b     # Graph only, skip Table B
./loombound gen "theme" --nodes 8          # Node count (default: 6)
./loombound gen "theme" --tone "..."       # Set atmospheric tone
./loombound gen "theme" --worldview "..."  # Set worldview / setting
./loombound gen "theme" --model deepseek   # Use DeepSeek for campaign graph

./loombound run                            # Launch game (requires ANTHROPIC_API_KEY + ollama)
./loombound run --lang zh                  # Chinese content

./loombound report                         # Token usage / cost for latest run
./loombound report --campaign ID

./loombound clean --campaign ID            # Remove a single campaign's data
./loombound clean --all                    # Remove all campaigns (keeps arc palette)
./loombound clean-logs                     # Truncate logs/llm.md
```

---

## Prerequisites

```bash
cp .env.example .env   # then fill in your API keys
```

- `ANTHROPIC_API_KEY` in `.env` — required for both `gen` and `run`
- ollama running (`ollama serve`) with `ollama pull gemma3:4b` — required for `run` (Fast Core local expansion)

> **Runtime requires Claude API only.** `./loombound run` uses Anthropic's prompt caching for the M2 classifier (Table A + Table C prefix) — this is an Anthropic-specific feature and breaks with other providers. `./loombound gen --model deepseek` is an offline operation and can use any supported provider.

### Supported Campaign Graph Providers (`--model`)

| Provider | Default model | API Key |
|---|---|---|
| `anthropic` (default) | claude-opus-4-6 | `ANTHROPIC_API_KEY` |
| `deepseek` | deepseek-chat | `DEEPSEEK_API_KEY` |
| `openai` | gpt-4o | `OPENAI_API_KEY` |
| `qwen` | qwen-plus | `DASHSCOPE_API_KEY` |

---

## Logs and Reports

All LLM calls are recorded in `logs/llm.md` with token counts, cost, and cache hit details.

```bash
./loombound report                         # Latest run
./loombound report --campaign ID           # Specific campaign
```

## Packaging a Demo

```bash
.venv/bin/python scripts/build_demo.py
.venv/bin/python scripts/build_demo.py --name loombound-demo-v1
```

---

The M0/M1/M2 three-layer memory model, C0/C1/C2 prompting cache strategy, and T0/T1/T2 Core separation used in this project are inspired by the author's another ongoing project. 
