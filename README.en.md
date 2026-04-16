# Loombound

A roguelite narrative engine driven by a three-layer AI architecture.

> 中文版文档：[README.md](README.md) · [docs/game-design.md](docs/game-design.md) · [docs/llm-architecture.md](docs/llm-architecture.md)

## Quick Start

```bash
# Prerequisites:
# - ANTHROPIC_API_KEY set in .env
# - ollama running: ollama pull gemma3:4b

# 1. One-time global setup — generate the arc-state palette (~50 enum entries used by the runtime classifier)
./loombound arc-palette

# 2. Generate a campaign (Opus builds the graph, Haiku generates Table B skeletons automatically)
./loombound gen "Singapore underground hacker community" --lang zh
./loombound gen "Solar sail era archaeology" --tone "melancholic, poetic, space mystery with a hint of hope" --lang zh
./loombound gen "Debt hunter escape" --worldview "Jupiter orbital colonies ruled jointly by the Debt Guild and the Salvage Church" --lang zh

# 3. Play (preloaded path: Claude arc classification + gemma3 local text expansion)
# --lang zh generates Chinese scene text; omit for English (default)
./loombound run --slow anthropic             # English
./loombound run --slow anthropic --lang zh   # Chinese

# Specify a campaign
./loombound run --campaign hunters_night_yharnam_last_lucid --slow anthropic --lang zh

# Limit nodes for testing
./loombound run --slow anthropic --nodes 2 --lang zh
```

---

## Three-Layer Architecture

| Phase | AI | Role |
|---|---|---|
| **One-time** | Claude Opus | Generate global arc-state palette (`arc-palette`, ~50 enum entries) |
| **Per campaign** | Claude Opus | Generate campaign graph (node topology, labels, map_blurb) |
| **Per campaign** | Claude Haiku | Generate Table B (per-node scene skeletons: scene_concept, option structure) |
| **Runtime** | Claude Opus | M2 classifier: current game state + arc palette → arc state ID (~10 tokens/node after cache hit) |
| **Runtime** | gemma3:4b (local) | Fast Core: Table B skeleton + arc state tendency → full scene text |

Only `ANTHROPIC_API_KEY` + ollama (local gemma3) required.

### Data Files

| File | Source | Contents |
|---|---|---|
| `data/m2_table_a.json` | Claude Opus (one-time) | Arc-state palette (50 enum entries, runtime prompt cache) |
| `data/campaigns/<id>.json` | Claude Opus (per campaign) | Campaign graph: node topology, no scene content |
| `data/nodes/<id>/*.json` | Claude Opus (per campaign) | Node spec: floor, type, arbitration count |
| `data/nodes/<id>/table_b.json` | Claude Haiku (per campaign) | Scene skeletons: scene_concept, sanity_axis, options |

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

./loombound run --slow anthropic           # Recommended: preloaded path
./loombound run --slow anthropic --lang zh # Chinese content
./loombound run                            # Authored content only, no LLM

./loombound report                         # Token usage / cost for latest run
./loombound report --campaign ID

./loombound clean --campaign ID            # Remove a single campaign's data
./loombound clean --all                    # Remove all campaigns (keeps arc palette)
./loombound clean-logs                     # Truncate logs/llm.md
```

---

## Prerequisites

- `ANTHROPIC_API_KEY` in `.env`
- ollama running (`ollama serve`) with `ollama pull gemma3:4b`

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

The M0/M1/M2 three-layer memory model, prompt cache strategy, and Fast/Slow Core separation used in this project are inspired by the author's ongoing PRISM project.
