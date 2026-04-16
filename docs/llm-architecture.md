# Loombound LLM 架构

## 设计原则

LLM 是必需内容层，但不替代确定性 kernel。职责边界：

| 负责方 | 职责 |
|---|---|
| **kernel** | 状态结构、合法更新、规则选择、replay 一致性 |
| **LLM** | 内容资产生成、场景文本展开、arc 分类、memory 摘要 |

所有 LLM 输出必须经过 `state_adapter` 正规化后才能进入运行时。

---

## IRIS 三层架构

本设计参考 PRISM 协议，将 AI 层分为三层，各层说不同的语言：

```
┌────────────────────────────────────────┐
│  M2 / Slow Core — Claude Opus          │  quasi 语言：arc 倾向、叙事方向
│  运行时 arc 分类器（离线内容规划）        │
└──────────────────┬─────────────────────┘
                   │  Table A + B（离线预载）
┌──────────────────▼─────────────────────┐
│  M1 / Fast Core — gemma3:4b（本地）     │  quasi ↔ 精确文本 转换
│  场景文本展开（运行时实时）               │
└──────────────────┬─────────────────────┘
                   │  structured payloads
┌──────────────────▼─────────────────────┐
│  M0 / Kernel — 确定性核心               │  精确语言：整数、枚举、合法 schema
│  RunMemory / NodeMemory                │
└────────────────────────────────────────┘
```

强行让 Slow Core 和 Kernel 直接对话会导致两种失败：
- Kernel 被迫接受模糊输入 → 验证失效
- Slow Core 被迫处理精确数值 → 语义失真

---

## M0 — Kernel 层（确定性）

对应 `RunMemory` / `NodeMemory`，完全确定性更新。  
不涉及 LLM，是系统的事实基础。

---

## M2 — Slow Core（Claude Opus，运行时 arc 分类器）

### 离线：生成 Table A 和 Table B

**Table A（全局 arc-state 调色板，一次性）**

50 条枚举，四个维度：
- `arc_trajectory`: rising / plateau / climax / resolution / pivot
- `world_pressure`: low / moderate / high / critical
- `narrative_pacing`: slow / steady / accelerating / sprint
- `pending_intent`: exploration / confrontation / revelation / recovery / transition

存于 `data/m2_table_a.json`，运行时加载进 prompt cache。

**Table B（per-campaign 场景骨架，每次 gen 自动生成）**

每个节点一组 scene skeleton，由 Claude Haiku 批量生成：
- `scene_concept`：场景核心方向（20-40 词）
- `sanity_axis`：本节点的心智压力轴
- `options`：选项意图、tags、effects

存于 `data/nodes/<campaign_id>/table_b.json`。

### 运行时：arc 分类（预载路径）

每个节点进入时，后台线程调用 M2 Classifier：

```
Table A (cached) + M1/M0 quasi state → entry_id（整数）
```

输出极短（~10 tokens），命中 prompt cache 后成本极低。

---

## Prompt Cache 策略

M2 Classifier 的 system prompt 展开为完整的分类指南（约 4,644 tokens），  
超过 Claude Opus 4.6 的缓存最低阈值（4,096 tokens）。

```
call1: cache_created=4644  input=104   ← 写入 cache
call2: cache_created=0     cache_read=4644  input=104   ← 命中
```

命中后每次调用只计费 ~104 tokens（quasi state 部分），节省约 90%。

---

## M1 — Fast Core（gemma3:4b，本地）

接收 M2 分类结果 + Table B 场景骨架，展开为玩家看到的完整文本：

| 字段 | 来源 | Fast Core 展开方式 |
|---|---|---|
| `scene_summary` | scene_concept | 3-5 句氛围散文 |
| `sanity_question` | sanity_axis | 1 句悬念问句 |
| option labels | intent | 5-10 词选项文字 |
| `add_events` | intent + effects | 1-2 句因果记录 |

本地运行，零 API 成本。

---

## 预载路径 vs 动态路径

### 预载路径（有 Table A + B，推荐）

```
Node N 游玩时，后台线程：
  1. build_quasi_description()  ← M1/M0 状态摘要
  2. M2 Classifier → entry_id
  3. M2Store.lookup_seed(entry_id) → Table B skeleton
  4. Fast Core.expand(skeleton, state) → payloads
  5. 存入 PrefetchCache

进入 Node N+1：
  PrefetchCache.consume() → 直接使用已生成内容
```

### 动态路径（无 Table B，fallback）

```
  SlowCoreClient.plan_node()  ← 运行时调用 LLM 生成内容
  → Fast Core 展开
```

---

## quasi 语言

M0 → M2 的状态传递使用"quasi 精确描述"，示例：

```
## Current state
  health:  high (stable)
  sanity:  moderate (depleting)
  floor:   2,  act: 2

## Scene history (M1 — last 3 nodes)
  [1] dark_alley — turbulent, pressure=high, trajectory=accelerating
  [2] archive    — stable, pressure=moderate, trajectory=rising

Classify the arc state that best matches the current game state.
```

M2 返回 `{"entry_id": N}` 或 `{"entry_id": -1}`（无匹配时降级到 authored 内容）。

---

## 内容边界

### LLM 可以生成

- campaign 图、节点拓扑、map_blurb（Opus，`./loombound gen`）
- scene_concept、sanity_axis、options（Haiku，Table B）
- scene_summary、sanity_question、option labels（gemma3，运行时展开）
- arc 分类 entry_id（Opus M2 Classifier）

### LLM 不可直接写入

- CoreState 数值字段（health / money / sanity delta 由 kernel 计算）
- RuleTemplate 的最终选择
- Run / Node / Arbitration 的结构字段

---

## 离线生成流程

```bash
# 1. 生成全局 arc palette（一次性）
./loombound arc-palette

# 2. 生成 campaign（Opus 生图 + Haiku 生 Table B，自动）
./loombound gen "主题" --lang zh

# 3. 运行时走预载路径
./loombound run --slow anthropic --lang zh
```

### 成本参考（6 节点 campaign）

| 步骤 | 模型 | 成本参考 |
|---|---|---|
| Campaign 图 | Opus | ~$0.04 |
| Table B | Haiku | ~$0.02 |
| M2 分类 ×N 节点（cache 命中） | Opus | ~$0.002/节点 |
| 场景文本展开 | gemma3 本地 | $0 |

---

## 模块位置

```
src/core/llm_interface/
├── m2_classifier.py    ← 运行时 arc 分类器（Opus）
├── prefetch.py         ← 后台预载线程管理
├── fast_core.py        ← gemma3 场景文本展开
├── collector.py        ← M0 → M1 quasi state 构建
└── types.py            ← SeedPack / ResolvedPack 数据类型

src/core/memory/
├── m2_store.py         ← Table A / Table B 加载与查询
└── types.py            ← M1Entry, M1Store, M2Entry, M2Store

scripts/
├── generate_arc_palette.py   ← 生成 Table A
├── generate_campaign.py      ← 生成 campaign + Table B
└── generate_table_b.py       ← 单独重生成 Table B
```
