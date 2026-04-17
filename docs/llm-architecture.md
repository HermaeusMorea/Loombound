# Loombound LLM 架构

## 设计原则

LLM 是必需内容层，但不替代确定性 kernel。职责边界：

| 负责方 | 职责 |
|---|---|
| **kernel** | 状态结构、合法更新、规则选择、replay 一致性 |
| **LLM** | 内容资产生成、场景文本展开、arc 分类、选项数值分配 |

所有 LLM 输出必须经过 `state_adapter` 正规化后才能进入运行时。

---

## IRIS 三层架构

本设计参考 PRISM 协议，将 AI 层分为三层，各层说不同的语言：

```
┌────────────────────────────────────────┐
│  M2 — Claude Haiku                     │  quasi 语言：arc 倾向、per-option 数值
│  运行时 arc 分类器（每次选择后调用）     │
└──────────────────┬─────────────────────┘
                   │  entry_id + effects（动态注入）
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

---

## M0 — Kernel 层（确定性）

对应 `RunMemory` / `NodeMemory`，完全确定性更新。  
不涉及 LLM，是系统的事实基础。

---

## M2 — 运行时 arc 分类器（Claude Haiku）

### 离线：生成 Table A 和 Table B

**Table A（全局 arc-state 调色板，一次性，由 Opus 生成）**

~50 条枚举，四个维度：
- `arc_trajectory`: rising / plateau / climax / resolution / pivot
- `world_pressure`: low / moderate / high / critical
- `narrative_pacing`: slow / steady / accelerating / sprint
- `pending_intent`: exploration / confrontation / revelation / recovery / transition

存于 `data/m2_table_a.json`，运行时加载进 Haiku prompt cache。

**Table B（per-campaign 场景骨架，每次 gen 由 Haiku 生成）**

每个节点一组 scene skeleton：
- `scene_concept`：场景核心方向（20–40 词）
- `sanity_axis`：本节点的心智压力轴
- `options`：选项意图（intent）、tags —— **不含 h/m/s 数值**

存于 `data/nodes/<campaign_id>/table_b.json`。

**Table C（运行时派生，不存文件）**

从 Table B 提取 `option_id + intent`，去掉所有数值，作为 Haiku 的 per-campaign cached prefix。Haiku 查表后填写各选项的 h/m/s 数值。

### 运行时：per-choice 分类 + 数值分配

每次玩家完成一次 arbitration 选择后，后台线程立即调用 M2 Classifier：

```
Table A (cached) + Table C (cached) + M1/M0 quasi state + 下一个 arbitration 标识
  → entry_id（整数） + effects（{option_id: {h, m, s}}）
```

- **entry_id**：更新本地 `_current_arc_id`，供 gemma3 prefetch 查 Table A 倾向
- **effects**：在下一个 arbitration 显示前注入选项数值
- gemma3 prefetch 直接读 `_current_arc_id`，不再主动调用 Haiku

节点内最后一次选择：只返回 entry_id（无 effects）。  
玩家选定下一节点后，主循环触发该节点第一个 arbitration 的 Haiku 调用。

---

## Prompt Cache 策略

Haiku M2 Classifier 的缓存分三层：

```
system prompt（分类指南 + 效果分配规则）    ~3,000 tokens  全局 cache
tool schema（select_arc_and_effects）        ~1,000 tokens  全局 cache
Table A                                      ~1,500 tokens  session cache
Table C（per-campaign 选项结构）             ~2,000 tokens  per-campaign cache
---
动态部分（quasi state + 目标 arbitration）     ~300 tokens  每次全量计费
输出（entry_id + 一个 arb 的 effects）          ~80 tokens  每次全量计费
```

cache 命中后每次调用实际成本：

| 部分 | tokens | 费率 | 费用 |
|---|---|---|---|
| 缓存读（~7,500 tokens） | 7,500 | $0.08/M | ~$0.0006 |
| 动态输入 | 300 | $0.80/M | ~$0.00024 |
| 输出 | 80 | $4/M | ~$0.00032 |
| **合计** | | | **~$0.001** |

---

## M1 — Fast Core（gemma3:4b，本地）

接收 arc 倾向（来自 Table A entry_id）+ Table B 场景骨架，展开为玩家看到的完整文本：

| 字段 | 来源 | Fast Core 展开方式 |
|---|---|---|
| `scene_summary` | scene_concept | 3–5 句氛围散文 |
| `sanity_question` | sanity_axis | 1 句悬念问句 |
| option labels | intent | 5–10 词选项文字 |
| `add_events` | intent | 1–2 句因果记录 |

h/m/s 数值由 Haiku 注入，gemma3 生成 add_events 时参考效果方向但不直接输出数值。

本地运行，零 API 成本。

---

## 运行时数据流

```
游戏开始
  └─ _current_arc_id = 0（固定初始值）
  └─ gemma3 warmup（后台）

进入节点 N
  └─ prefetch.trigger(N+1)
       └─ 读 _current_arc_id → 查 Table A 倾向
       └─ 查 Table B 骨架
       └─ gemma3 展开（后台，和玩家游玩并行）
  └─ 玩家选取节点后，主循环触发 Haiku(N_first_arb=0)（后台）

游玩 Arb 0
  └─ consume_arb_effects(N, 0) → 等待 Haiku 结果 → 注入 effects
  └─ 显示选项 → 玩家选择
  └─ update_arc_state(quasi, N, next_arb=1)（后台）

游玩 Arb 1
  └─ consume_arb_effects(N, 1) → 等待 Haiku 结果 → 注入 effects
  └─ 玩家选择（最后一个 arb）
  └─ update_arc_state(quasi, None, None) → 仅更新 entry_id

节点 N 结束，玩家选择节点 N+1
  └─ update_arc_state(quasi, N+1, arb=0)（后台）
  └─ 进入节点 N+1，prefetch 结果已就绪
```

---

## quasi 语言

M0 → M2 的状态传递使用"quasi 精确描述"，示例：

```
## Current state (quasi)
  health:  high (stable)
  sanity:  moderate (falling)
  floor:   2,  act: 2
  dominant themes: dread×3, isolation×2

## Node trajectory (2 completed)
  [crossroads] floor=1  sanity_delta=-1  flags=none
  [market]     floor=2  sanity_delta=-2  flags=witnessed_violence

## Active node so far (partial)
  arbitrations_resolved=1  sanity_lost=1

Assign effects for: node_id=archive_vault, arb_index=1
```

Haiku 返回 `{"entry_id": N, "effects": [{"id": "opt_a", "h": -2, "m": 0, "s": -1}, ...]}`。

---

## 内容边界

### LLM 可以生成

- Campaign 图、节点拓扑、map_blurb（Opus，`./loombound gen`）
- scene_concept、sanity_axis、选项意图（Haiku，Table B 生成）
- arc state entry_id + per-option h/m/s 数值（Haiku，运行时 M2）
- scene_summary、sanity_question、option labels、add_events（gemma3，运行时展开）

### LLM 不可直接写入

- CoreState 数值字段的最终应用（由 kernel 执行）
- RuleTemplate 的最终选择
- Run / Node / Arbitration 的结构字段

---

## 离线生成流程

```bash
# 1. 生成全局 arc palette（一次性）
./loombound arc-palette

# 2. 生成 campaign（Opus 生图 + Haiku 生 Table B，自动）
./loombound gen "主题" --lang zh

# 3. 运行
./loombound run --lang zh
```

---

## 成本分析

### 参考数据：campaign "核战后遗址的审计员"（5 节点，11 次 arbitration）

> 注：以下运行时数据采集于 Haiku M2 上线前（当时使用 Opus per-node 设计），仅供离线成本参考。

**离线阶段（一次性，所有玩家共享）**

| 步骤 | 模型 | 实测花费 |
|---|---|---|
| Campaign 图生成 | Claude Opus | $0.0454 |
| Table B 场景骨架生成 | Claude Haiku | $0.0166 |
| **离线小计** | | **$0.0620** |

**运行时估算（Haiku per-choice 设计）**

| 步骤 | 模型 | 估算花费 |
|---|---|---|
| M2 分类 × 11 次选择（cache 命中） | Claude Haiku | ~$0.011 |
| Fast Core 展开 × 11 arbitration | gemma3（本地） | **$0** |
| **运行时小计** | | **~$0.011** |

**首次游玩总花费估算：~$0.073**

---

### 随游玩次数增加，均摊成本趋近于运行时极限

| 游玩次数 | 总 API 花费 | 每次均摊 |
|---|---|---|
| 1 次 | ~$0.073 | ~$0.073 |
| 10 次 | ~$0.173 | ~$0.017 |
| 100 次 | ~$1.17 | ~$0.012 |
| ∞ | — | **~$0.011** |

---

### 假如用全 Opus 方案替换 Fast Core？

这 11 次 arbitration 展开，Fast Core 平均每次约 617 eval tokens，输入约 300 tokens。换成 Opus 的等效成本：

```
每次 arbitration：300 input + 617 output
= 300 × $15/M + 617 × $75/M ≈ $0.051/次
11 次合计 ≈ $0.56/局
```

| 游玩次数 | 当前架构 | 全 Opus 方案 | 倍率 |
|---|---|---|---|
| 1 次 | ~$0.073 | ~$0.62 | ~8.5× |
| 100 次 | ~$1.17 | ~$56 | **~48×** |

---

## 模块位置

```
src/core/llm_interface/
├── m2_classifier.py    ← 运行时 arc 分类器（Haiku，per-choice）
├── prefetch.py         ← 后台预载线程 + arc 状态追踪
├── fast_core.py        ← gemma3 场景文本展开
├── collector.py        ← M0 → quasi state 构建
└── types.py            ← SeedPack / PrefetchEntry 数据类型

src/core/memory/
├── m2_store.py         ← Table A / Table B / Table C 加载与查询
└── types.py            ← M1Entry, M1Store, M2Entry, M2Store

scripts/
├── generate_arc_palette.py   ← 生成 Table A（Opus）
└── generate_campaign.py      ← 生成 campaign 图（Opus）+ Table B（Haiku）
```
