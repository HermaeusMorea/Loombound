# 启动游戏

## 快速开始

```bash
# 生成 campaign（Campaign Core 默认用 Claude Opus 4.6）
./gen.sh "新加坡地下黑客社区" --nodes 6 --lang zh

# 显式指定故事基调
./gen.sh "太阳帆时代考古调查" --tone "忧郁、诗性、带一点希望感的太空悬疑"

# 显式指定世界观
./gen.sh "债务猎人逃亡" --worldview "木星轨道殖民地由债务公会和打捞教团共同统治"

# 运行游戏（DeepSeek 做 Slow Core，gemma3:4b 做 Fast Core）
./run.sh --slow deepseek --lang zh

# 指定 campaign 文件
./run.sh --campaign data/campaigns/my_campaign.json --slow deepseek --lang zh

# 限制节点数（测试用）
./run.sh --slow deepseek --nodes 2

# 不用 LLM（纯 authored 内容）
./run.sh
```

## 预载路径（可选，节省运行时 token）

预载路径用 Claude 做轻量 arc 分类器（~10 tokens/节点），DeepSeek 离线填充内容表。
没有这两个表时，游戏自动回退到动态路径，完全兼容。

```bash
# 第一步：一次性生成 Table A（arc state 枚举，约 50 行，无叙事文字）
python generate_table_a.py

# 第二步：per-campaign 生成 Table B（DeepSeek 填充完整场景内容）
python generate_table_b.py --campaign data/campaigns/singapore_shadow_net.json

# 之后正常运行，自动走预载路径
./run.sh --slow deepseek --lang zh
```

Table A 存在 `data/m2_table_a.json`，Table B 存在 `data/nodes/<campaign_id>/table_b.json`。

## 三层抽象架构

游戏引擎按 IRIS 分三个抽象层，每层由不同模型负责：

| 层 | 职责 | 模型 | 调用时机 |
|---|---|---|---|
| **M0 Kernel** | 精确状态、事件记录 | 无（纯确定性） | 始终运行 |
| **M1 Fast Core** | M1 → M0：展开场景文字 | gemma3:4b（本地） | 运行时，每个 arbitration |
| **M2 Slow Core** | M2 → M1：内容规划 / 弧线分类 | DeepSeek + Claude（见下） | 运行时后台 或 离线预生成 |

M2 层由两个模型分担，互不替代：

| M2 角色 | 模型 | 何时用 | 切换方式 |
|---|---|---|---|
| Campaign Core（离线） | claude-opus-4-6 | `./gen.sh` 一次性生成节点图 | `--model deepseek` |
| Table A 生成（离线） | claude-opus-4-6 | `python generate_table_a.py` 一次性 | 暂不支持切换 |
| Arc 分类器（运行时）| claude-opus-4-6 | 预载路径，每节点 ~10 tokens | 暂不支持切换 |
| Table B 生成（离线）| deepseek-chat | `python generate_table_b.py` per-campaign | `--model` 传给脚本 |
| Slow Core 动态路径（运行时）| deepseek-chat | 无预载表时的 fallback | `./run.sh --slow anthropic` |

> Fast Core（gemma3）必须配合 `--slow` 启用，单独传 `--fast` 无效。

### `--model` / `--slow` 语法

```bash
# gen.sh 用 --model 选 Campaign Core provider
./gen.sh "theme" --model deepseek
./gen.sh "theme" --model anthropic:claude-haiku-4-5

# run.sh 用 --slow 选 Slow Core provider（同时开启 LLM 模式）
./run.sh --slow openai
./run.sh --slow deepseek:deepseek-reasoner --fast gemma3:4b
```

### 支持的 Provider

| Provider | 默认模型 | API Key 环境变量 |
|---|---|---|
| `anthropic` | claude-opus-4-6 | `ANTHROPIC_API_KEY` |
| `deepseek` | deepseek-chat | `DEEPSEEK_API_KEY` |
| `openai` | gpt-4o | `OPENAI_API_KEY` |
| `qwen` | qwen-plus | `DASHSCOPE_API_KEY` |

## 报表

```bash
# 最新一轮（显示 M2 Classifier / Slow Core / Fast Core 三栏）
./report.sh

# 指定 campaign 的最近一轮
./report.sh --campaign singapore_shadow_net
```

## 前置条件

- `.env` 里有对应 API Key（至少 `ANTHROPIC_API_KEY` + `DEEPSEEK_API_KEY`）
- ollama 在跑（`ollama serve`），Fast Core 模型已下载：`ollama pull gemma3:4b`

## 日志

LLM 调用记录在 `logs/llm.md`，包含每次调用的 token 数和 cache 命中情况。

## 打包 Demo

```bash
python3 build_demo.py
python3 build_demo.py --name loombound-demo-v1
python3 build_demo.py --include-logs
```
