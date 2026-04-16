# Loombound

Roguelite 叙事游戏引擎，三层 AI 架构驱动。

> 英文版文档：[README.en.md](README.en.md) · [docs/game-design.en.md](docs/game-design.en.md) · [docs/llm-architecture.en.md](docs/llm-architecture.en.md)

## 快速开始

```bash
# 前置条件
# .env 里有 ANTHROPIC_API_KEY
# ollama 在跑：ollama pull gemma3:4b

# 1. 一次性全局设置（生成 arc-state 调色板，~50 行枚举，运行时 Claude 分类器使用）
./loombound arc-palette

# 2. 生成 campaign（Opus 生成图，Haiku 自动生成 Table B，两步合一）
./loombound gen "新加坡地下黑客社区" --lang zh
./loombound gen "太阳帆时代考古调查" --tone "忧郁、诗性、带一点希望感的太空悬疑" --lang zh
./loombound gen "债务猎人逃亡" --worldview "木星轨道殖民地由债务公会和打捞教团共同统治" --lang zh

# 3. 启动游戏（预载路径：Claude arc 分类 + gemma3 本地展开）
# --lang zh 生成中文场景文字；省略则默认英文
./loombound run --slow anthropic --lang zh   # 中文
./loombound run --slow anthropic             # English

# 指定 campaign
./loombound run --campaign hunters_night_yharnam_last_lucid --slow anthropic --lang zh

# 测试用：限制节点数
./loombound run --slow anthropic --nodes 2 --lang zh
```

---

## 三层架构

| 阶段 | AI | 做什么 |
|---|---|---|
| **一次性** | Claude Opus | 生成全局 arc-state 调色板（`arc-palette`，~50 行枚举） |
| **每个 campaign** | Claude Opus | 生成 campaign 图（节点拓扑、标签、map_blurb） |
| **每个 campaign** | Claude Haiku | 生成 Table B（每节点场景骨架：scene_concept、选项结构） |
| **运行时** | Claude Opus | M2 分类器：当前游戏状态 + arc 调色板 → 返回 arc state ID（prompt cache 命中后 ~10 tokens/节点） |
| **运行时** | gemma3:4b（本地） | Fast Core：Table B 骨架 + arc state 倾向 → 展开完整场景文字 |

全程只需要 `ANTHROPIC_API_KEY` + ollama（本地 gemma3）。

### 数据文件

| 文件 | 来源 | 内容 |
|---|---|---|
| `data/m2_table_a.json` | Claude Opus（一次性） | arc-state 调色板（50 行枚举，运行时 prompt cache） |
| `data/campaigns/<id>.json` | Claude Opus（每 campaign） | Campaign 图：节点拓扑，无场景内容 |
| `data/nodes/<id>/*.json` | Claude Opus（每 campaign） | 节点 spec：floor、type、arbitration 数量 |
| `data/nodes/<id>/table_b.json` | Claude Haiku（每 campaign） | 场景骨架：scene_concept、sanity_axis、选项 |

---

## `./loombound` 参数

```bash
./loombound arc-palette                    # 生成全局 arc-state 调色板（一次性）
./loombound clean-palette                  # 删除 arc 调色板

./loombound gen "theme" --lang zh          # 默认：Opus 生图 + Haiku 生 Table B
./loombound gen "theme" --skip-table-b     # 只生成 campaign 图
./loombound gen "theme" --nodes 8          # 节点数（默认 6）
./loombound gen "theme" --tone "..."       # 指定基调
./loombound gen "theme" --worldview "..."  # 指定世界观
./loombound gen "theme" --model deepseek   # 用 DeepSeek 生成 campaign 图

./loombound run --slow anthropic           # 推荐：预载路径
./loombound run --slow anthropic --lang zh # 中文内容
./loombound run                            # 纯 authored 内容，不用 LLM

./loombound report                         # 最新一轮 token 用量 / 成本
./loombound report --campaign ID

./loombound clean --campaign ID            # 删除单个 campaign 数据
./loombound clean --all                    # 清空所有 campaign（保留 arc 调色板）
./loombound clean-logs                     # 清空 logs/llm.md
```

---

## 前置条件

- `.env` 里有 `ANTHROPIC_API_KEY`
- ollama 在跑（`ollama serve`），已下载：`ollama pull gemma3:4b`

### 支持的 Campaign 图 Provider（`--model`）

| Provider | 默认模型 | API Key |
|---|---|---|
| `anthropic`（默认） | claude-opus-4-6 | `ANTHROPIC_API_KEY` |
| `deepseek` | deepseek-chat | `DEEPSEEK_API_KEY` |
| `openai` | gpt-4o | `OPENAI_API_KEY` |
| `qwen` | qwen-plus | `DASHSCOPE_API_KEY` |

---

## 日志与报表

LLM 调用记录在 `logs/llm.md`（含每次调用的 token 数、成本、cache 命中情况）。

```bash
./loombound report                        # 最新一轮
./loombound report --campaign ID          # 指定 campaign
```

## 打包 Demo

```bash
.venv/bin/python scripts/build_demo.py
.venv/bin/python scripts/build_demo.py --name loombound-demo-v1
```

---

游戏的 LLM 分层架构（M0/M1/M2 三层记忆、prompt cache 策略、Fast/Slow Core 分工）设计参考自作者正在进行的 PRISM 项目。
