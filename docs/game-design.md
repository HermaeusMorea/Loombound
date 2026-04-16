# Loombound 游戏设计

## 项目定位

CLI 文字冒险 / 跑团风格 roguelite，主题偏克苏鲁心智压力与叙事裁决。  
主入口：`./loombound run`

---

## 运行时对象模型

三个核心对象构成整局游戏的生命周期：

```
Run
└── Node (×N)
    └── Arbitration (×1..M)
```

### Run

整局游戏的宿主。持有：
- `CoreState` — 数值状态（health / money / sanity / floor / act）
- `MetaState` — 叙事解释层状态（active_conditions、major_events、traumas）
- `RunMemory` — 跨节点长期记忆
- `RuleSystem` — 整局规则系统状态

### Node

地图上的单个节点 / 场景容器。生命周期：
1. 从 Run 进入，继承状态视图
2. 节点内顺序处理一个或多个 Arbitration
3. 结束时生成 NodeSummary，重要结果写回 RunMemory
4. 节点销毁

持有：`NodeMemory`、`NodeRuleState`

### Arbitration

单次事件选择 / 裁决单元。包含：
- `ArbitrationContext`（scene_type、floor/act、resources、tags、状态视图）
- options（选项列表）
- selected option + result
- status

---

## 状态层

### CoreState（结构化、决定论）

- health / money / sanity
- floor / act / location
- inventory tags
- 由 kernel 负责验证和更新，LLM 不直接写入

### MetaState（叙事解释层）

- active_conditions（临时状态标签）
- metadata.major_events / traumas / narrator_mood
- 适合由 LLM 生成和解释的文本性状态

---

## 记忆模型

### RunMemory（跨节点长期记忆）

保存：sanity、recent_rules、recent_shocks、theme_counters、behavior_counters、important_incidents、narrator_mood

用于：为后续裁决提供长期上下文、为规则系统提供轻量 bias、为 LLM 生成提供摘要

### NodeMemory（节点内短期记忆）

保存：events、choices_made、shocks_in_node、sanity_lost_in_node、important_flags、node_summary

用于：描述节点内发生了什么、在节点结束时向 RunMemory 提炼重要信息

---

## 规则系统

三部分：

- **RuleTemplate** — 静态规则模板，定义适用场景、主题、匹配条件、偏好/禁止的 option tags、sanity_penalty
- **RuleSystem** — 整局级，持有 templates，记录最近使用和使用次数
- **NodeRuleState** — 节点级，当前可用规则、候选规则、选中规则、selection trace

---

## 决定论主链

每条 Arbitration 的执行顺序：

```
context → signals → theme scoring → rule matching
→ rule selection → enforcement → narration → state update
```

1. 从 context 和 options 提取 signals
2. 映射到主题分数（clarity / composure / self_preservation / detachment）
3. RuleTemplate 对当前 arbitration 做匹配
4. RuleSystem + RunMemory 对候选规则轻量排序
5. 选出主规则
6. enforcement：对所有 options 给出 `stable / destabilizing` 裁决，计算 sanity_cost/delta
7. narration 生成演出文本
8. 将选中 option 的 effects 写回 Run

---

## 状态适配层（state_adapter）

外部内容进入系统的唯一正规边界：
- 读取 authored JSON assets → 内部运行时对象
- 接收 LLM 生成的结构化内容包 → 内部运行时对象
- 保证 kernel 永远处理统一的内部对象，不直接处理自由文本

---

## 展示层（presentation）

CLI ANSI 终端界面：
- 顶部 HUD（状态数值、当前节点信息）
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
├── campaigns/<id>.json        ← 节点拓扑图（由 Opus 生成）
├── nodes/<id>/<node_id>.json  ← 节点 spec（floor, type, arbitration 数量）
├── nodes/<id>/table_b.json    ← 场景骨架（由 Haiku 生成）
├── m2_table_a.json            ← 全局 arc-state 调色板（由 Opus 一次性生成）
├── arbitrations/              ← authored 手写仲裁内容
├── rules/rules.small.json     ← 规则集
└── text/narration_templates.json
```

---

## `src/core/` 模块结构

| 模块 | 职责 |
|---|---|
| `runtime` | Run/Node/Arbitration 生命周期，gameplay loop，campaign 初始化 |
| `deterministic_kernel` | 共享数据模型（CoreStateView、ArbitrationContext、OptionResult 等） |
| `state_adapter` | 外部内容 → 内部运行时对象的正规化边界 |
| `signal_interpretation` | 从 scene/context 提取 signals 和主题分数 |
| `rule_engine` | 规则匹配、选择、selection trace |
| `enforcement` | 规则落到 options，apply 选项效果到状态 |
| `memory` | RunMemory/NodeMemory 类型和 update_after_node 逻辑 |
| `narration` | 文字演出生成 |
| `presentation` | CLI HUD 渲染 |
| `authoring` | authored JSON 资产加载 |
| `llm_interface` | LLM 协作层（M1/M2 classifier、prefetch、collector） |
