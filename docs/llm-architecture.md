# Loombound LLM 架构

## 设计原则

LLM 是必需内容层，但不替代确定性 kernel。职责边界：

| 负责方 | 职责 |
|---|---|
| **kernel（C0）** | 状态结构、合法更新、规则执行、replay 一致性 |
| **LLM（C1/C2/C3）** | 内容资产生成、场景文本展开、bearing 分类、选项数值分配 |

所有 LLM 输出必须经过 `state_adapter` 正规化后才能进入运行时。

---

## 三层处理架构（C0–C2）

```
┌────────────────────────────────────────┐
│  C2 — Claude Haiku                     │  tendency（倾向带）→ bearing + per-option toll/effects
│  运行时 bearing 分类器（每次选择后调用） │
└──────────────────┬─────────────────────┘
                   │  entry_id + effects + tolls（动态注入）
┌──────────────────▼─────────────────────┐
│  C1 — qwen2.5:7b（本地）                 │  A1 骨架 → 精确散文
│  场景文本展开（运行时实时）               │
└──────────────────┬─────────────────────┘
                   │  structured payloads
┌──────────────────▼─────────────────────┐
│  C0 — 确定性核心                        │  精确语言：整数、枚举、合法 schema
│  RunMemory / WaypointMemory            │
└────────────────────────────────────────┘
```

---

## C0 — Kernel 层（确定性）

对应 `RunMemory` / `WaypointMemory`，完全确定性更新。  
不涉及 LLM，是系统的事实基础。

---

## C2 — 运行时 bearing 分类器（Claude Haiku）

### 离线：生成 arc-state catalog 和 scene skeletons

**arc-state catalog（全局 bearing 枚举，一次性，由 C3/Opus 生成）**

~50 条枚举，四个维度：
- `arc_trajectory`: rising / plateau / climax / resolution / pivot
- `world_pressure`: low / moderate / high / critical
- `narrative_pacing`: slow / steady / accelerating / sprint
- `pending_intent`: exploration / confrontation / revelation / recovery / transition

存于 `data/arc_state_catalog.json`，运行时加载进 Haiku prompt cache。

**scene skeletons（per-saga 场景骨架，每次 `gen` 由 C2/Haiku 生成）**

每个 waypoint 一组场景骨架：
- `scene_concept`：场景核心方向（20–40 词）
- `sanity_axis`：本 waypoint 的心智压力轴
- `options`：选项意图（intent）、tags —— **不含 h/m/s 数值**

存于 `data/waypoints/<saga_id>/scene_skeletons.json`。

**A1 option index（运行时派生，不存文件）**

从 scene skeletons 提取 `option_id + intent`，去掉所有数值，作为 Haiku 的 per-saga cached prefix。  
Haiku 查表后填写各选项的 h/m/s 数值和 toll。

### 运行时：per-choice bearing 分类 + 数值分配

每次玩家完成一次 encounter 选择后，后台线程立即调用 C2 classifier：

```
arc-state catalog (cached) + A1 option index (cached) + toll lexicon (cached)
  + tendency（A0 压缩）+ 下一个 encounter 标识
  → entry_id（整数） + effects（{option_id: {h, m, s}}）+ tolls
```

- **entry_id**：更新当前 bearing，供 C1 prefetch 查 arc-state catalog 倾向
- **effects**：在下一个 encounter 显示前注入选项数值
- **tolls**：per-option toll 标签，交给 rule enforcement
- C1 prefetch 直接读当前 bearing，不再主动调用 C2

Waypoint 内最后一次选择：只返回 entry_id（无 effects）。  
玩家选定下一 waypoint 后，主循环触发该 waypoint 第一个 encounter 的 C2 调用。

---

## Prompt Cache 策略

C2 classifier 的缓存分四层：

```
system prompt（分类指南 + toll 分配规则）      ~3,000 tokens  全局 cache
tool schema（arc update + effects）             ~1,000 tokens  全局 cache
arc-state catalog                                  ~1,500 tokens  session cache
A1 option index + toll lexicon（per-saga）      ~2,500 tokens  per-saga cache
─────────────────────────────────────────────────────────────
tendency（A0 压缩）+ 目标 encounter 标识           ~300 tokens  每次全量计费
输出（entry_id + 一组 effects + tolls）            ~100 tokens  每次全量计费
```

cache 命中后每次调用实际成本（实测 8 次均值）：

| 部分 | tokens | 费率 | 费用 |
|---|---|---|---|
| 缓存读（~8,087 tokens） | 8,087 | $0.08/M | ~$0.00065 |
| 动态输入 | ~398 | $0.80/M | ~$0.00032 |
| 输出 | ~220 | $4/M | ~$0.00088 |
| **合计** | | | **~$0.0019** |

---

## C1 — 场景展开（qwen2.5:7b，本地）

接收当前 bearing（来自 arc-state catalog entry_id）+ scene skeletons 场景骨架，展开为玩家看到的完整文本：

| 字段 | 来源 | C1 展开方式 |
|---|---|---|
| `scene_summary` | scene_concept | 3–5 句氛围散文 |
| `sanity_question` | sanity_axis | 1 句悬念问句 |
| option labels | intent | 5–10 词选项文字 |
| `add_events` | intent | 1–2 句因果记录 |

h/m/s 数值和 toll 由 C2 注入，C1 生成 add_events 时参考效果方向但不直接输出数值。

本地运行，零 API 成本。`num_predict = -1`（无限制，防止复杂场景截断）。

---

## 运行时数据流

```
游戏开始
  └─ bearing = 0（固定初始值）
  └─ C1（qwen2.5:7b）warmup（后台）

进入 waypoint N
  └─ prefetch.trigger(N)
       └─ 读 bearing → 查 arc-state catalog 倾向
       └─ 查 scene skeletons 骨架
       └─ C1 展开（后台，和玩家游玩并行）
  └─ 玩家选取 waypoint 后，主循环触发 C2(waypoint_N, encounter=0)（后台）

游玩 encounter 0
  └─ consume_effects(N, 0) → 等待 C2 结果 → 注入 effects + tolls
  └─ 显示选项 → 玩家选择
  └─ C2 update（bearing + N, next=1）（后台）

游玩 encounter 1（最后）
  └─ consume_effects(N, 1) → 等待 C2 结果 → 注入 effects + tolls
  └─ 玩家选择
  └─ C2 update（bearing only）→ 仅更新 entry_id

Waypoint N 结束，玩家选择 waypoint N+1
  └─ C2 update（bearing + N+1, encounter=0）（后台）
  └─ 进入 waypoint N+1，prefetch 结果已就绪
```

---

## tendency 语言

C0 → C2 的状态传递使用"tendency 描述"（A0 精确数值压缩为倾向带），示例：

```
## Current state (tendency)
  health:  high (stable)
  sanity:  moderate (falling)
  depth:   2,  act: 2  active_marks: lamp_oil

## Waypoint trajectory (2 completed)
  [crossroads] depth=1  sanity_delta=-1  flags=none
  [market]     depth=2  sanity_delta=-2  flags=witnessed_violence

## Active waypoint so far (partial)
  encounters_resolved=1  sanity_lost=1

## Effect delta calibration (calibrate h/m/s to current state)
  h (health  high/100): [-18, +5]  — reserve extremes for pivotal options
  m (money   moderate): [-4, +8]
  s (sanity  moderate/100): [-12, +5]  — fragile sanity → smaller losses

Assign effects for: waypoint_id=archive_vault, encounter_index=1
```

C2 返回 `{"entry_id": N, "effects": [{"id": "opt_a", "h": -2, "m": 0, "s": -1, "toll": "destabilizing"}, ...]}`。

`## Effect delta calibration` 由 `collector.py` 根据当前倾向带实时生成，告知 C2 当前状态下各资源的合理 delta 范围，防止输出失真数值。C2 仍可在极端剧情节点突破建议范围，但应将大幅变动保留给关键选项。

---

## 内容边界

### LLM 可以生成

- Saga 图、waypoint 拓扑、map_blurb、toll lexicon、rules、narration_table（C3，`./loombound gen`）
- scene_concept、sanity_axis、选项意图（C2，scene skeletons 生成）
- bearing entry_id + per-option h/m/s 数值 + tolls（C2，运行时）
- scene_summary、sanity_question、option labels、add_events（C1，运行时展开）

### LLM 不可直接写入

- CoreState 数值字段的最终应用（由 kernel 执行）
- RuleTemplate 的最终执行（C2 可提名规则 ID，kernel 负责应用；确定性 select_rule 为回退路径）
- Run / Waypoint / Encounter 的结构字段

---

## 离线生成流程

```bash
# 1. 生成全局 bearing 枚举（一次性）
./loombound arc-palette

# 2. 生成 saga（Opus 生图 + Haiku 生 scene skeleton，自动）
./loombound gen "主题" --lang zh

# 3. 运行
./loombound run --lang zh
```

---

## 成本分析

### 实测参考（deep_mine_cult_act1，4 waypoints，8 次 encounter 选择）

完整日志：[logs/sample_deep_mine_cult_act1.md](../logs/sample_deep_mine_cult_act1.md)

**离线阶段（一次性）**

| 步骤 | 模型 | 实测花费 |
|---|---|---|
| Saga 图 + toll lexicon + rules + narration_table | Claude Opus 4.6 | $0.0878 |
| scene skeletons 场景骨架 | Claude Haiku 4.5 | $0.0251 |
| **离线小计** | | **$0.1129** |

**运行时（单局）**

| 步骤 | 模型 | 实测花费 |
|---|---|---|
| C2 bearing 分类 × 8 次（cache_read 64,696 tokens，节省 $0.0466） | Claude Haiku | $0.0148 |
| C1 场景展开 × 8 encounter（12,423 local tokens） | qwen2.5:7b（本地） | **$0** |
| **运行时小计** | | **$0.0148** |

### 1000 局成本对比

| 策略 | 离线 ×1 | 每局 | 1000 局总计 |
|---|---|---|---|
| **tiered（当前）** Opus gen + Haiku C2 + 本地 C1 | $0.1129 | $0.0148 | **$14.88** |
| 全 Opus（C2 + C1 均换 Opus） | $0.2450 | $0.2199 | $220.11 |
| 全 Haiku（saga gen 也换 Haiku） | $0.0392 | $0.0352 | $35.22 |

> tiered vs 全 Haiku：每局 C1 本地免费省 $0.0204，1000 局节省 ~$20。  
> tiered vs 全 Opus：1000 局节省 ~$205，约 **14.8×** 差距。  
> 完整的 per-run 明细由 `./loombound report` 实时计算。

---

## 模块位置

```
src/t3/core/
├── generate_campaign.py    ← C3：saga 生成（Opus）
└── gen_a2_cache_table.py   ← C3：arc-state catalog 生成（Opus，一次性）

src/t2/core/
├── m2_classifier.py        ← C2：运行时 bearing 分类器（Haiku，per-choice）
├── prefetch.py             ← C1 + C2：后台预载线程 + bearing 状态追踪
├── gen_a1_cache_table.py   ← C2：scene skeletons 生成（Haiku，per-saga）
├── collector.py            ← C0 → tendency state 构建
└── types.py                ← EncounterSeed / PrefetchEntry 数据类型

src/t1/core/
├── expander.py             ← C1：qwen2.5:7b 场景文本展开
├── prompts.py              ← C1 prompt 构建
└── ollama.py               ← C1 transport（ollama /api/chat）

src/t2/memory/
├── a2_store.py             ← arc-state catalog / scene skeletons / A1 option index 加载
└── types.py                ← ArcStateEntry、A1Entry、A1Store、RuntimeTableStore

src/t0/memory/
└── models.py               ← CoreState、EncounterContext、OptionResult 等核心数据模型
```
