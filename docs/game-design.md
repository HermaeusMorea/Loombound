# Loombound 游戏设计

## 项目定位

CLI 文字冒险 / 跑团风格 roguelite，主题偏克苏鲁心智压力与叙事裁决。  
主入口：`./loombound run`

---

## 运行时对象模型

三个核心对象构成整局游戏的生命周期：

```
Run
└── Waypoint (×N)
    └── Encounter (×1..M)
```

### Run

整局游戏的宿主。持有：
- `CoreState` — 数值状态（health / money / sanity / depth / act）
- `MetaState` — 叙事解释层状态（active_marks、major_events、traumas）
- `RunMemory` — 跨 waypoint 长期记忆
- `RuleSystem` — 整局规则系统状态

### Waypoint

地图上的单个地点 / 场景容器。生命周期：
1. 从 Run 进入，继承状态视图
2. Waypoint 内顺序处理一个或多个 Encounter
3. 结束时生成 WaypointSummary，重要结果写回 RunMemory
4. Waypoint 销毁

持有：`WaypointMemory`、`WaypointRuleState`

### Encounter

单次事件选择 / 裁决单元。包含：
- `EncounterContext`（scene_type、depth/act、resources、tags、状态视图）
- options（选项列表，含 C2 生成的 toll 和 effects）
- selected option + result
- status

---

## 状态层

### CoreState（结构化、决定论）

- health / money / sanity
- depth / act / location
- inventory tags
- 由 kernel 负责验证和更新，LLM 不直接写入

### MetaState（叙事解释层）

- active_marks（持久状态标签，如 `lamp_oil`、`warding_tools`）
- metadata.major_events / traumas / narrator_mood
- 适合由 LLM 生成和解释的文本性状态

---

## 记忆模型

### RunMemory（跨 waypoint 长期记忆）

保存：sanity、recent_rules、recent_shocks、behavior_counters、important_incidents、narrator_mood

用于：为后续裁决提供长期上下文、为规则系统提供轻量 bias、为 LLM 生成提供摘要

### WaypointMemory（waypoint 内短期记忆）

保存：events、choices_made、shocks_in_waypoint、sanity_lost_in_waypoint、important_flags、waypoint_summary

用于：描述 waypoint 内发生了什么、在 waypoint 结束时向 RunMemory 提炼重要信息

---

## 规则系统

三部分：

- **RuleTemplate** — 静态规则模板，定义适用场景、theme（per-saga narration_table 中的 key）、匹配条件、偏好/禁止的 option tags、sanity_penalty
- **RuleSystem** — 整局级，持有 templates，记录最近使用和使用次数
- **WaypointRuleState** — waypoint 级，当前可用规则、候选规则、选中规则、selection trace

规则选择按 `(-freshness_penalty, priority, id)` 排序，不使用主题分数。

---

## 决定论主链

每条 Encounter 的执行顺序：

```
context → rule matching → rule selection → enforcement → narration → state update
```

1. RuleTemplate 对当前 encounter 做匹配（context tags + option tags）
2. RuleSystem + RunMemory 对候选规则轻量排序（freshness penalty + priority）
3. 选出主规则
4. enforcement：应用 C2 生成的 toll，计算 sanity_cost/delta
5. narration：从 saga 的 narration_table 按 `rule.theme` 查单句心理描述（fallback 到 `"neutral"`）
6. 将选中 option 的 effects 写回 Run

---

## 状态适配层（state_adapter）

外部内容进入系统的唯一正规边界：
- 读取 JSON assets → 内部运行时对象
- 接收 LLM 生成的结构化内容包 → 内部运行时对象
- 保证 kernel 永远处理统一的内部对象，不直接处理自由文本

---

## 展示层（presentation）

CLI ANSI 终端界面：
- 顶部 HUD（状态数值、当前 waypoint 信息）
- 中间内容区（场景描述、裁决结果、map）
- 底部输入区

特点：
- 双栏 HUD，窄终端自动切换为上下堆叠
- 固定 Input box，输入前有提示
- 慢节奏逐段显示，给后台生成争取时间

---

## 数据资产结构

```
data/
├── sagas/<id>.json                      ← waypoint 拓扑图（C3/Opus 生成）
├── sagas/<id>_toll_lexicon.json         ← per-saga toll 词汇表（C3 生成）
├── sagas/<id>_rules.json                ← per-saga 规则集（C3 生成，含 rule.theme keys）
├── sagas/<id>_narration_table.json      ← per-saga 叙事主题表（C3 生成，10-15 条）
├── waypoints/<id>/a1_cache_table.json   ← waypoint 场景骨架（C2/Haiku 生成）
└── a2_cache_table.json                  ← 全局 bearing 枚举（C3 一次性生成）
```

---

## 模块结构

| 目录 | 层 | 职责 |
|---|---|---|
| `src/t0/memory/` | A0 | CoreState、RunMemory、WaypointMemory 等数据模型 |
| `src/t0/core/` | C0 | enforcement、rule_engine、state_adapter、signal_interpretation |
| `src/t1/core/` | C1 | C1 expander（qwen2.5:7b 场景文字展开）、prompts、ollama transport |
| `src/t2/memory/` | A2 | bearing 条目、toll lexicon 等数据模型（a2_store） |
| `src/t2/core/` | C2 | m2_classifier、prefetch、gen_a1_cache_table、collector |
| `src/t3/core/` | C3 | saga 生成逻辑（generate_campaign、gen_a2_cache_table） |
| `src/runtime/` | 组装点 | play_cli、session、campaign；可 import 全部层的唯一位置 |
