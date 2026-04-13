# 三层 AI 协议栈

本文档描述一种用于 AI 驱动的实时内容系统的通用架构模式。虽然以 `black-archive`
为具体背景，但这套设计在结构上独立于游戏本身，适用于任何需要同时满足以下三个
约束的系统：

- 有确定性的状态机（需要快速、严格、可验证）
- 有创造性的 AI 内容层（需要语义理解、叙事规划、长程一致性）
- 有成本与延迟的现实约束（不能每次都等远程大模型）

---

## 核心类比：语义协议栈

这套架构类似网络通信的分层协议模型。不同层说不同的语言，层与层之间需要专门
的翻译机制，而不是让上层和下层直接对话。

```
┌─────────────────────────────────────┐
│         Core LLM（远程核心层）        │  quasi 语言：倾向、氛围、叙事方向
│  慢 / 贵 / 松散 / 长程规划           │
└──────────────┬──────────────────────┘
               │  双向翻译
┌──────────────▼──────────────────────┐
│       Intermediary LLM（本地中介层）  │  quasi 语言 ↔ 精确语言 的转换点
│  中速 / 适中成本 / 协议转换           │
└──────────────┬──────────────────────┘
               │  双向翻译
┌──────────────▼──────────────────────┐
│         Kernel（确定性核心层）        │  精确语言：整数、合法 schema、枚举值
│  极快 / 无成本 / 严格验证             │
└─────────────────────────────────────┘
```

强行让 Core LLM 和 Kernel 直接对话会导致两种失败：
- Kernel 被迫接受模糊输入 → 验证失效
- Core LLM 被迫处理精确数值 → 语义失真，且数值在 LLM 返回前就已过期

中介层存在的根本理由：**AI 层和确定性层说的不是同一种语言。**

---

## 第一层：Kernel（确定性核心）

### 职责

- 维护精确的系统状态（`CoreState`）
- 验证所有输入输出的合法性
- 执行状态更新
- 保证 replay 一致性

### 语言特征

- 整数、枚举值、白名单字段
- 有明确 schema 的结构化数据
- 拒绝任何格式外的输入

### 能处理的

```
health: 3
money: 5
sanity: 4
active_conditions: ["reed_whispers"]
health_delta: -1
```

### 不能处理的

MetaState 中的语义层——人物心情、弧线张力、叙事倾向——对 Kernel 而言是透明
的，它只能传递这些数据，无法理解或修改其语义。

---

## 第二层：Intermediary LLM（本地中介层）

### 职责

这一层是整个协议栈的枢纽，两个子角色构成一个 codec：

**Collector（Encoder，Kernel → Slow Core 方向）**

Phase 1 期间持续记录状态变化；Phase 1 结束时触发：
- 将 CoreState 的精确数值离散化为倾向带（quasi-CoreState）
- 将 MetaState 的原始数据提炼为语义摘要（quasi-MetaState）
- 打包成 Slow Core 能理解的格式发出，Slow Core 开始异步生成下下节点的 quasi 描述

**Generator（上下文敏感的 Decoder，Slow Core → Kernel 方向）**

Phase 1 期间持续监听 Slow Core 发来的下一节点 quasi 描述；
Phase 1 结束后（与 Collector 并发）触发：
- 结合收到的下一节点 quasi 描述与 Phase 1 实际结果
- 执行 delta 调和：对比 Slow Core 的预测前提与 Phase 1 真实发生，调整内容侧重
- 将展开后的叙事结构转换为 schema 合法的结构化内容
- 提交给 Kernel 验收——验证职责属于 Kernel，不属于 Generator

Generator 不是对称解压——它在 Kernel 允许的 delta 范围内根据实际上下文自由
决定具体数值，是上下文敏感的解码，不是原样还原 Slow Core 的意图。

向下转换是**软转换**：中介 LLM 在 Kernel 允许的 delta 范围内根据上下文自由
决定具体数值，而不是机械地查表。例如玩家在节点 B 前段将自己打到危急血量，
中介 LLM 生成节点 C 时可以将血量奖励选项的数值设置得更大——这是对当前处境
的叙事性回应，不是误差。Kernel 的验收范围是硬上限，软转换在这个边界内发挥。

### quasi-CoreState 格式

CoreState 中的精确数值不适合直接发给 Core LLM，原因：
1. Core LLM 是异步的，返回时数值已经过期
2. Core LLM 不需要精确数值，它需要的是"当前压力倾向"

离散化方式（以 black-archive 为例）：

```
health:  critical(0-2) | low(3-5) | medium(6-8) | high(9-10)
sanity:  critical | low | medium | high
money:   scarce | low | medium | abundant
```

quasi-CoreState 示例：

```json
{
  "health": "critical",
  "sanity": "low",
  "money": "medium",
  "pressure": "high_occult_exposure",
  "arc_momentum": "destabilizing",
  "active_conditions": ["reed_whispers", "lamp_oil"]
}
```

### quasi-MetaState 格式

本地 LLM 将 RunMemory / NodeMemory 的原始数据总结为叙事层摘要：

```json
{
  "arc_so_far": "玩家反复选择高风险路径，积累了 occult 条件，近两个节点回避了所有安全选项",
  "dominant_themes": ["self_preservation", "detachment"],
  "tone": {
    "dread": "low",
    "temptation": "none",
    "leniency": "medium"
  },
  "key_events": [
    "穿越芦苇时有不明物跟随",
    "在市场购买了嗡嗡作响的绒布神像"
  ]
}
```

注意 `tone` 字段虽然在 Kernel 里以精确整数存储（`NarratorMood.dread: int`），
发给 Core LLM 前同样需要离散化。Core LLM 不知道 `dread: 2` 是高还是低，
也不知道上限是多少，原样透传精确数值没有意义。
中介 LLM 负责把所有精确数值统一转换为倾向带，包括 tone 计数器。

### 重要原则

发给 Core LLM 的所有数据都经过中介 LLM 处理，但处理方式不同：

- **机制性数据**（health、sanity、money、tone 计数器等）：从 Kernel 直接读取
  精确值，由中介 LLM **离散化**为倾向带后发出。不做语义总结，只做粒度转换，
  避免引入幻觉或精度损失。
- **叙事性数据**（发生了什么、弧线走向）：由中介 LLM 对原始
  `major_events` / `node_summary` 列表做**语义总结**后发出。原始列表对
  Core LLM 是噪音，总结后信息更密、token 更少。

两类数据都不绕过中介 LLM，区别在于离散化还是总结。

---

## 第三层：Core LLM（远程核心层）

### 职责

- 接收 quasi-CoreState + quasi-MetaState
- 规划未来节点的叙事结构与倾向
- 返回同一语言层级的 quasi 信息（不返回精确数值）

### 为什么不让它处理精确数值

1. **时效性问题**：Core LLM 返回需要数秒，期间游戏状态已经变化
2. **能力匹配问题**：LLM 对"血量应该减少"的判断可靠，对"血量应该精确
   变为 3"的判断不可靠且没有意义
3. **验证问题**：Core LLM 返回的精确数值直接进 Kernel 会绕过中介层的上下文修正

### Core LLM 返回的 quasi 输出示例

```json
{
  "next_node": {
    "scene_concept": "flooded archive, documents dissolving, something watching from the stacks",
    "sanity_axis": "knowledge vs. self-preservation when sanity is already low",
    "context_tags": ["occult", "knowledge_pressure", "enclosed"],
    "options": [
      {
        "option_id": "read_document",
        "intent": "risk further sanity loss for critical information",
        "tags": ["knowledge", "high_risk"],
        "tendency": { "sanity": "negative", "arc": "deeper_into_occult" }
      },
      {
        "option_id": "leave_immediately",
        "intent": "preserve sanity, lose the information forever",
        "tags": ["restraint", "safe"],
        "tendency": { "sanity": "stable", "arc": "withdrawal" }
      }
    ]
  }
}
```

注意 `tendency` 而非 `delta`。Core LLM 只给方向，不给数字。

---

## 预载机制：节点前后段设计

### 问题

AI 内容生成有延迟，不能等玩家到了节点 C 才开始生成 C。

### 解法：在节点 B 内部创造生成窗口

节点 B 分为两段：

```
节点 N
  ├─ 前段（Phase 1）：核心选择
  │   └─ Generator 监听 Slow Core 发来的 N+1 quasi
  │   └─ Collector 记录 Phase 1 期间的状态变化
  │   └─ 玩家做出影响 CoreState / MetaState 的关键决策
  │   └─ [quasi 已到 + Phase 1 结束] → Collector 上行 + Generator 启动（并发，无等待）
  │
  └─ 后段（Phase 2）：结果缓冲
      └─ 行为结果不影响 Slow Core 正在进行的 N+2 预生成
         同时为两件事提供时间窗口：
         Generator 在后台完成节点 N+1 的最终生成；
         Slow Core 异步处理节点 N+2 的 quasi 描述
```

### 时序

```
[上一循环 N-1 Phase 1 结束时已触发]
    Slow Core 开始异步生成节点 N+1 quasi 描述
    │
进入节点 N Phase 1
    ├─→ Generator 持续监听 Slow Core 发来的节点 N+1 quasi 描述
    ├─→ Collector 记录 Phase 1 期间的状态变化
    ├─→ 玩家游玩 Phase 1（关键决策）
    │     CoreState / MetaState 变化被 Kernel 精确记录
    └─→ [理想情况下 Phase 1 结束前] Generator 收到 N+1 quasi 描述
    │
Phase 1 结束（且 Generator 已收到 quasi）→ 并发触发
    ├─→ Collector：将记录的 Phase 1 状态打包上行给 Slow Core
    │     Slow Core 开始异步生成节点 N+2 quasi 描述
    │
    └─→ Generator：节点 N+1 quasi 描述 + Phase 1 实际结果
          → delta 调和 → 开始展开生成完整节点 N+1 内容

节点 N Phase 2 期间
    ├─→ 玩家活动（真实游玩 / 叙述 / 任何形式）
    ├─→ Generator 在后台完成节点 N+1 内容生成
    └─→ Slow Core 异步处理节点 N+2 quasi（将在 N+1 Phase 1 期间到达 Generator）

进入节点 N+1
    └─→ N+1 内容已就绪，零等待
```

效果：玩家感觉节点 C 像是节点 B 里发生的一切自然推导出来的，
即使节点 C 的核心结构在节点 B 开始时就已经被 Core LLM 规划好了。

### delta 调和问题

Core LLM 生成节点 C 的时候，节点 B 的结果还是预测值，不是精确值。

如果玩家在节点 B 前段的实际行为和 Core LLM 的预期偏差较大（比如预测玩家会
选安全路线，但实际上玩家选了高风险 occult 路线），节点 C 的 quasi 倾向就
建立在错误的假设上。

本地中介 LLM 在最终生成节点 C 时需要执行 **delta 调和**：

```
delta = actual_quasi_B_result - predicted_quasi_B_result
node_C_final = expand(quasi_C, adjusted_by=delta)
```

这个修正是可行的，因为：
- 偏差可以通过 quasi-CoreState 比较量化
- 修正幅度通常有限（一两个倾向级别的差距）
- 本地 LLM 只调整内容侧重，不需要重新规划节点结构

---

## 流式输出与 P0 降级

大多数内容应在后台预生成（P1/P2 任务）。流式输出的核心价值在 P0 阻塞场景：
玩家到达节点但内容尚未准备好时，流式输出把硬性等待转化为可接受的叙事体验。

优先级分层：

| 优先级 | 内容 | 策略 |
|---|---|---|
| P0 | 当前仲裁缺内容 | blocking + 流式输出 |
| P1 | 下一节点 | 后台排队，节点进入时触发 |
| P2 | 未来分支 | 低优先级后台 |
| P3 | 记忆总结、meta 更新 | 节点结束后异步 |

---

## 适用范围的推广：超越文字游戏

这套架构并不依赖"玩家在读文字"作为时间缓冲。任何有离散节点结构的游戏都适用，
关键条件只有两个：

1. 玩家在节点内的参与时间 > AI 生成时间
2. 内容可以模板化——AI 只提供参数，资产重量由引擎承担

### roguelike 场景

以 roguelike 为例，节点 A 是一个战斗房间：

```
节点 A 前段：关键决策（走哪条路、触发什么事件）→ 影响未来状态
    └─ [前段结束] Collector 上行 → Slow Core 生成节点 A+2 quasi（5-15 秒）
    └─ [同时] Generator 启动 → 结合 A+1 quasi + 前段实际结果，生成节点 A+1

节点 A 后段：清理残余小怪、探索房间 → 不影响正在进行的 A+2 预生成
    └─ [期间] Generator 在后台完成节点 A+1 的生成（1-5 秒）

进入节点 A+1 → A+1 已经就绪
```

后段不需要是被动的过场或动画——它可以是真实战斗，只要这段战斗的结果
不改变 Core LLM 用来规划 C 的那些关键信息。前后段的边界是
**信息重要性的边界，不是游玩活动的边界**。

### AI 输出量的对比

```
文字游戏：AI 生成完整场景文字（数百 token）

roguelike：AI 只生成模板参数（数十 token）
{
  "monsters": [
    {"template": "skeleton_warrior", "hp_mod": 1.3, "affix": "shield"},
    {"template": "cursed_archer",    "hp_mod": 0.8, "affix": "poison"}
  ],
  "items": [{"template": "sword", "damage_mod": 1.5, "affix": "fire"}],
  "room_theme": "corrupted_library",
  "trap_density": "low"
}
```

token 量少一个数量级，生成更快，schema 更简单，合规率更高。AI 不生成资产，
只生成配置；资产的重量由引擎和模板系统承担。

### 适用条件总结

| 游戏类型 | 节点参与时间 | AI 输出类型 | 适用性 |
|---|---|---|---|
| 文字冒险 | 30-120 秒 | 场景文字 + 选项 | 适用，缓冲较紧 |
| roguelike | 30 秒-数分钟 | 模板参数 | 适用，缓冲宽裕 |
| 策略游戏事件系统 | 数分钟 | 事件参数 | 适用，缓冲极宽裕 |
| 动作游戏（房间极短）| 5-15 秒 | 任何 | 不适用，预算不足 |

唯一无法规避的等待是游戏启动时的第一个节点——没有前序节点可以借用时间，
这是普通的"进入游戏加载"，玩家对此有预期。

---

## 各层的处理能力对比

| 维度 | Kernel | Intermediary LLM | Core LLM |
|---|---|---|---|
| 速度 | 极快（微秒级）| 中等（秒级）| 慢（5-15秒）|
| 成本 | 零 | 低 | 高 |
| 输入格式 | 严格 schema | 半结构化 | 松散自然语言 |
| 输出格式 | 严格 schema | quasi ↔ 精确双向 | quasi 结构 |
| 能理解 CoreState | 完全 | 转译 | 倾向近似 |
| 能理解 MetaState | 不能 | 部分总结 | 完全 |
| 长程叙事规划 | 不能 | 不能 | 核心能力 |
| 格式合法性保证 | 强制 | 尽力 | 不保证 |

---

## 一般性原则

这套架构对任何"确定性状态机 + AI 创意层"系统都适用，提炼出以下原则：

**1. 不同层使用不同语言，不强迫跨层直接通信**
精确层和语义层之间必须有专门的翻译机制。

**2. AI 层处理倾向，确定性层处理数值**
LLM 判断"方向"可靠，判断"精确数值"不可靠。让 LLM 给方向，
确定性层结合当前状态转换为数值。

**3. 发给 AI 的信息粒度要匹配 AI 的时间尺度**
异步返回的 AI 层不适合接收瞬时变化的精确数据，
适合接收在其延迟时间尺度内保持稳定的倾向性描述。

**4. 在确定性窗口内完成 AI 生成**
利用系统中"玩家在做其他事"的时间窗口（阅读叙事、等待动画）
提前完成后台 AI 生成，而不是在关键路径上等待。

**5. 预测偏差是常态，设计要能容纳修正**
AI 层的预测基于不完整信息，系统必须在结果已知后支持局部修正，
而不是假设预测总是准确的。修正由中介 LLM 在语义层完成——它对比 Core LLM
的预测前提与实际发生的情况，调整最终展开内容的侧重。Kernel 不参与语义修正，
只负责验收修正后输出的合法性。

**6. 上行保精确，下行保互动**
向 Core LLM 上行时，目标是最大化倾向与语义的精确度——不传数值是因为数值时
效性太短，但传递的倾向和语义摘要必须如实反映当前系统状态，不能失真。Core
LLM 的规划质量完全依赖这份信息的准确性。

向 Kernel 下行时，目标不是精确还原 Core LLM 的意图，而是让中介 LLM 结合
远程返回的倾向信息与当前实际场景状态，产生真正的互动感——同样的"血量倾向负面"
在玩家血量充裕时转换为 -1，在玩家已经危急时可以转换为一个更戏剧性的数值。
下行转换是上下文敏感的叙事决策，不是死板的查表。Kernel 的验收范围是这种自由
的硬边界。

**7. 前后段边界是信息边界，不是活动边界**
节点内的前后段划分依据是"这段行为的结果是否影响 Core LLM 正在生成的下一节点"，
而不是"玩家是否在主动操作"。后段可以是真实战斗、探索、任何游玩内容，
只要其结果不改变已经启动的预生成所依赖的关键状态。
这让整个预载机制对玩家完全透明，没有任何人为插入的等待感。

**8. 模板化是零加载的前提**
AI 只负责生成参数，引擎负责实例化资产。AI 输出量越小，生成越快，
预算越宽裕。为 AI 设计好模板系统比让 AI 生成完整资产更重要。
