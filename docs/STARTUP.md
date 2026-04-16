# 启动游戏

## 标准工作流

```bash
# 一次性全局设置（生成 arc-state 调色板，约 50 行，供运行时 Claude 分类器使用）
python generate_arc_palette.py

# 生成 campaign（Claude Opus 生成图，Haiku 自动接着生成 Table B，两步合一）
./gen "新加坡地下黑客社区" --lang zh
./gen "太阳帆时代考古调查" --tone "忧郁、诗性、带一点希望感的太空悬疑" --lang zh
./gen "债务猎人逃亡" --worldview "木星轨道殖民地由债务公会和打捞教团共同统治" --lang zh

# 运行游戏（自动走预载路径：Claude arc 分类 + gemma3 本地展开）
./run --slow anthropic --lang zh

# 指定 campaign 文件
./run --campaign data/campaigns/singapore_underground_hackers.json --slow anthropic --lang zh

# 限制节点数（测试用）
./run --slow anthropic --nodes 2 --lang zh
```

---

## 三层架构：哪个 AI 做什么

| 阶段 | AI | 做什么 |
|---|---|---|
| **一次性** | Claude Opus | 生成全局 arc-state 调色板（`generate_arc_palette.py`，~50 行枚举） |
| **每个 campaign** | Claude Opus | 生成 campaign 图（节点拓扑、标签、map_blurb） |
| **每个 campaign** | Claude Haiku | 生成 Table B（每节点场景骨架：scene_concept、选项结构） |
| **运行时** | Claude Opus | M2 分类器：当前游戏状态 + arc 调色板 → 返回 arc state ID（~10 tokens/节点） |
| **运行时** | gemma3:4b（本地） | Fast Core：Table B 骨架 + arc state 倾向 → 展开完整场景文字 |

全程只需要 `ANTHROPIC_API_KEY` + ollama（本地 gemma3）。

### 数据文件

| 文件 | 来源 | 内容 |
|---|---|---|
| `data/m2_table_a.json` | Claude Opus（一次性） | arc-state 调色板（50 行枚举，运行时缓存） |
| `data/campaigns/<id>.json` | Claude Opus（每 campaign） | Campaign 图：节点拓扑，无场景内容 |
| `data/nodes/<id>/*.json` | Claude Opus（每 campaign） | 节点 spec：floor、type、arbitration 数量 |
| `data/nodes/<id>/table_b.json` | Claude Haiku（每 campaign） | 场景骨架：scene_concept、sanity_axis、选项 |

---

## `./gen` 参数

```bash
./gen "theme" --lang zh            # 默认：Claude Opus 生图 + Haiku 生 Table B
./gen "theme" --skip-table-b       # 只生成 campaign 图，跳过 Table B
./gen "theme" --nodes 8            # 节点数（默认 6）
./gen "theme" --tone "..."         # 指定基调
./gen "theme" --worldview "..."    # 指定世界观
./gen "theme" --model deepseek     # 改用 DeepSeek 生成 campaign 图（Haiku 仍做 Table B）
```

## `./run` 参数

```bash
# --slow PROVIDER[:MODEL] 开启 LLM 模式（有 Table A + B → 预载路径；否则动态回退）
./run --slow anthropic             # 推荐：预载路径
./run --slow anthropic --lang zh   # 中文内容
./run --slow deepseek              # 动态路径 fallback（无 Table B 时）
./run                              # 纯 authored 内容，不用 LLM
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

## 报表

```bash
./report                           # 最新一轮（M2 Classifier / Fast Core token 用量）
./report --campaign singapore_shadow_net
```

## 日志

LLM 调用记录在 `logs/llm.md`。

## 打包 Demo

```bash
python3 build_demo.py
python3 build_demo.py --name loombound-demo-v1
python3 build_demo.py --include-logs
```
