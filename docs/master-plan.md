# Master Plan

## 文档定位

本文档用于保存 `li-director-sts2` 的长期总纲领、阶段路线、关键结构设想与代表性规则样例。它不是 README 的扩写版，也不替代当前执行文档。

分工如下：

- `README.md`: 项目入口与快速启动
- `project-definition.md`: 当前项目定义与原型命题
- `mvp-scope.md`: 当前 MVP 边界与不做项
- `system-architecture.md`: 当前原型流水线与模块职责
- `master-plan.md`: 长期战略蓝图、未来阶段脉络与设计保留项
- `decision-log.md`: 关键取舍与其原因

当前阶段仍以 **Python 离线原型优先** 为准。当前默认实现是一个 `Deterministic Kernel` 驱动的 CLI/demo；后续才进入真实游戏接入，并逐步开放更多 `LLM Control Surfaces`。

## Native State Machines And Overlay Position

本项目未来若接入真实游戏，也不应被理解为替换原生 run-level 或 encounter-level state machines。更合理的定位是：

- 原生游戏拥有并推进 `CoreState`
- 本项目作为 overlay-style ritual judge 叠加其上
- 本项目维护自己的 `MetaState`
- 本项目通过未来 adapter / hook points 消费标准化的 `EventTrace`
- 本项目生成有界的 `ProposedEffects`
- 最终允许写回原生流程的部分，必须经过决定论的 `EffectApplier`

这意味着：

- 即使未来出现更强的导演能力，本项目默认也不是“新的主状态机”
- `CoreState` 仍由原生游戏拥有
- 礼官系统更像一层制度化解释、记忆与约束 overlay

## 项目一句话定义

这是一个《杀戮尖塔 2》方向的 **AI 礼官导演系统**：它不替玩家打牌，而是在关键决策节点把当前局势解释成一种“礼制情境”，再用可执行的规则模板对玩家施加限制、评价与惩罚。

从长期系统定位上说，它不只是单点即时裁判，而是一个 **每局记忆型礼官系统**：礼官会在整局 run 内持续形成案卷、积累态度，并据此前后连贯地调整后续审判。

## 项目价值与体验目标

本项目的趣味不在于“AI 会玩游戏”，而在于它把普通 roguelike 的最优化过程，扭转成一个被荒诞叙事持续干涉的 meta-game。

- 玩家不是单纯算最优，而是在和一个一本正经胡说八道的“礼官制度”博弈
- 每次 run 不是单纯吃随机 buff/debuff，而是收到有风格、有理由、有连续性的法令
- 玩家面对的是一种“我知道这很扯，但它又好像自成逻辑”的导演系统

如果这个系统成立，玩家体验的重点不是“赢得更稳”，而是“在一个过度严肃的秩序机器面前决定守礼还是违礼”。这一点是长期总设计的核心；即使未来加入更自由的 LLM 导演模式，也不应把项目重心改写成自动打牌或纯胜率优化。

真正让这个系统成立的，不只是“每个节点都能说一句像样的话”，而是“礼官会记得你之前做过什么，并在后面据此改变态度、法令与口气”。

## 与自动打牌 AI 的边界

自动打牌 AI 的目标是替玩家做更优动作，提高胜率，尽量逼近求解器或高水平操作者。

本项目不是 player replacement，而是一个 **run director / rule-imposing narrator**：

- 目标不是替玩家出牌，而是制造“约束感 + 叙事感 + 节目效果 + 连续人格”
- 它不负责把局面打到最优，而是负责把局面解释成一种礼制问题
- 它不隐藏自己的存在，而是刻意以“礼官 / 裁判 / 旁白导演”的身份介入

因此，这个系统必须让玩家感到“被一套奇怪但自洽的制度持续审视”，而不是“被 AI 接管操作”。

## 为什么适合 agent 思路

这个系统天然符合一个小型 agent loop：

- Observe
- Interpret
- Decide
- Act
- Reflect

但在当前 Python 原型阶段，需要明确三点：

- 先做 deterministic-first 的简化版本
- agent loop 先以代码规则流水线为主，而不是自由自治 agent
- 默认模式下先让 kernel 托底，LLM 从低风险 control surfaces 开始逐步介入

换言之，当前仓库里的“agent 性”主要体现在 Observe / Interpret / Decide / Act / Reflect 这一条结构化循环上，而不是体现在让一个模型自主规划全局行为。

## Deterministic Kernel 与 LLM Control Surfaces

### Deterministic Kernel 负责什么

`Deterministic Kernel` 是当前 MVP 的默认核心实现，负责：

- 统一数据结构与合法状态
- 默认规则匹配与选择流水线
- 惩罚执行与礼崩累计
- structured run memory 的读写与更新
- decision trace、日志与可回放性
- 测试、回归验证与 fallback implementation
- 对来自 LLM 的建议、重排或补充解释做边界校验

从架构角色上说，kernel 是：

- source of truth
- validator / arbiter
- fallback implementation
- replayable engine

它的意义不是永久排斥 LLM，而是为未来更高自由度的 LLM 介入提供稳定底座。

它还负责区分：

- 哪些事实属于 `CoreState`
- 哪些叠加状态属于 `MetaState`
- 哪些输出只是 `ProposedEffects`
- 哪些内容可以真正经由 `EffectApplier` 写回

### LLM Control Surfaces 包括什么

本项目从长期架构上预留多个 LLM 接入面，未来可以逐步开放，例如：

- `context enrichment`
  对当前局势做高层语义摘要，补充 hard-coded tags 之外的解释视角
- `theme hinting / interpretation assistance`
  对礼制主题提供语义提示、解释性评分建议或补充理由
- `candidate rule reranking`
  在已匹配候选规则中做解释性重排
- `bounded penalty modulation`
  在明确边界内对惩罚幅度做小范围调节
- `narration rewriting`
  对旁白做润色、风格化重写与多样化表达
- `reflection / run summarization`
  总结玩家行为模式，生成礼官人格印象或 run 史官总结

在未来真实接入阶段，LLM 更适合：

- 解释 `EventTrace`
- 补充 `MetaState` 的叙事与态度层
- 生成 `ProposedEffects`

而不是在默认模式下直接变更 `CoreState`。

### 当前默认模式

- kernel 主导
- LLM 可为空
- 无 LLM 也能完整运行
- 规则系统必须可执行、可测试、可调试、可回放

### 未来实验模式

- 可逐步开放更多 control surface
- 允许更混沌、更戏剧化的导演行为
- 可轻量引入 `classic`、`ritual`、`chaos` 等 mode 思路

但仍应具备：

- mode 开关
- 边界约束
- 日志记录
- 回退机制

这不是当前仓库的立即实现目标，只是长期架构上的明确预留。

## LLM 参与内容生产的路径

除直接参与 interpretation、reranking、narration 或 reflection 外，LLM 还有一条更适合当前项目节奏的接入方式：先参与结构化内容生产，再由 kernel 决定是否采用。

这条路径可以发生在两个时机：

- run 开始前，生成本局专属的规则包、文案包、初始礼官 persona / mood 配置
- 某些局内节点前，生成受 schema 约束的临时规则、补充旁白模板或候选 `ProposedEffects`

这些产物更适合被保存为 JSON assets，而不是自由文本指令。它们应满足：

- 能映射到既有 schema、`RuleTemplate`、`MetaState` 字段或其他明确数据结构
- 在执行前经过 deterministic kernel 的加载、校验、筛选与裁决
- 默认模式下不绕过 rule engine，不直接获得 `CoreState` mutation 权限

这样做的意义在于：

- 保留 LLM 对“本局风格”“临时法令”“礼官人格”的生成能力
- 不破坏决定论、回放、调试与测试能力
- 让局前生成或局中预生成自然成为未来 overlay integration 的一部分

换言之，长期上可以让 LLM “写本局礼官包”，但仍应由 kernel 决定这些内容如何被执行。

## 每局记忆型礼官系统

单次即时裁决可以证明规则引擎能工作，但不足以形成“制度感”“案卷感”与连续人格。若礼官每到一个节点都像失忆一样只看当前局势，系统更像一次性脚本，而不像真正持续存在的导演角色。

因此，长期目标应升级为 run-scoped ritual judge：

- 礼官在整局 run 中持续记录玩家行为
- 玩家每次守礼、违礼、贪利、冒险、反覆，都会形成案卷
- 后续法令选择、惩罚强度、叙事语气与礼官方向都受这些记忆影响
- 未来的 LLM judge memory / persona memory 也应建立在这一层之上

这样做的价值在于：

- 规则更像制度，而不是随机旁白
- 惩罚更像累犯处理，而不是每次重置
- 语气更像同一位礼官，而不是拼接文本
- 更自然地支持 future LLM memory 与 persona continuity

## 结构化记忆与人格记忆

### 结构化记忆

结构化记忆是执行基础，应由 kernel 维护。它至少可以记录：

- `ritual_collapse`
- recent edicts
- recent violations
- 按主题累计的行为统计
- vows / promises / standing constraints
- judge mood values，例如严苛、多疑、惩贪、宽赦
- 重要事件前科

这层直接影响：

- 规则排序
- 惩罚升级
- 场景判断
- 后续法令偏好

### 人格记忆

人格记忆是未来可选的叙事放大器，不应取代结构化记忆作为唯一事实来源。它可以记录：

- 礼官对玩家的当前印象
- 本局风格摘要
- 对玩家行为的叙事性评价
- 当前礼官的人格倾向与口吻偏差

它更适合影响：

- 旁白连续性
- 礼官人格一致性
- run 总结
- 长线导演感

核心区分是：

- 结构化记忆负责“判什么”
- 人格记忆负责“怎么判、怎么说、像不像同一个礼官”

## 长期架构蓝图

以下描述以 **Python prototype / future mod integration** 为口径。当前实现只覆盖其中一部分，但未来扩展也应尽量沿同一边界前进。

### 1. State Adapter / Context Builder

职责：

- 把游戏状态或样例 JSON 转成统一的数据结构
- 当前阶段主要来自离线 sample contexts
- 未来才替换为真实游戏接入层

输出：

- `RunSnapshot`
- `ChoiceContext`

在 overlay 语境下，这一层未来还负责：

- 从原生流程读取 `CoreState` 的只读视图
- 将原生变化整理为标准化 `EventTrace`
- 为 overlay 层提供不依赖具体 API 细节的输入

说明：

- 当前仓库中，adapter 的主要输入还不是游戏内实时状态，而是人为构造或录制的样例上下文
- 将来接 mod 时，应优先把真实游戏状态转换到既有结构，而不是反过来让规则层绑死在游戏 API 上
- 未来可在这一层接入 `context enrichment`，但 enrichment 结果应被记录并可回放

### 2. Signal Extraction / Interpretation

职责：

- 从上下文中提取可计算信号
- 给礼制主题打分
- 当前默认模式下使用确定性逻辑，不使用自由生成分类作为主路径

示例主题：

- 避争
- 克己
- 守序
- 正名
- 谦退
- 慎独
- 祭备
- 尊卑

说明：

- 主题是解释层，不是文学层
- 主题打分必须可追踪，可解释为什么命中
- 主题分类可扩展，但第一阶段不追求抽象体系一次到位
- 未来可在这一层引入 `theme hinting / interpretation assistance`，但默认模式下仍由 kernel 负责最终可执行表示

### 3. Rule Engine

职责：

- 从规则模板库里筛选当前可执行规则
- 处理触发条件、主题匹配、重复惩罚、冷却、冲突消解
- 选出一条当前最合适的法令

说明：

- 规则引擎是当前原型的核心
- 在当前默认模式下，规则主要来自模板或结构化配置，而不是自由生成
- 未来可开放 `candidate rule reranking`，并在实验模式下探索受限的 `rule proposal`
- kernel 仍负责验证候选规则是否合法、是否越界、是否可回放

### 4. Narration Layer

职责：

- 把已确定的裁决包装成礼官旁白
- 当前阶段优先模板系统
- 未来可接 LLM 做可选润色
- 在默认模式下，LLM 不直接改写 `rule_id`、限制、惩罚等结构化裁决字段

说明：

- 旁白服务于裁决，不反客为主
- 旁白的任务是把结构化裁决说得更像礼官，而不是重新解释规则
- 长期上，这一层只是最显性的 control surface，不应被误解为 LLM 的唯一位置

### 5. Enforcement / Outcome Layer

职责：

- 标记违礼选项
- 允许守礼或违礼
- 增加 `ritual_collapse` / 礼崩值
- 记录日志
- 当前阶段在 CLI/demo 中模拟
- 未来才在 mod UI 中真实触发

说明：

- 第一阶段只做软惩罚
- 未来如要做硬锁、二次确认或更复杂后果，也应建立在这层的稳定记录之上
- 未来可在明确边界内开放 `bounded penalty modulation`，但默认模式下仍由 kernel 决定最终落地值
- 面向原生流程的 effect write-back 应通过 `EffectApplier`，而不是由解释层直接落地

### 6. Memory Layer

职责：

- 保存礼崩值
- 保存最近法令
- 保存最近违礼记录
- 保存风格倾向 / future bias

说明：

- 当前 repo 中的 memory 只需做到轻量、可回放
- 将来可扩展到 run 内长期导演人格，但不应过早复杂化
- 未来可在这一层接入 `reflection / run summarization` 与 persona evolution
- 这层属于 `MetaState` 的核心组成部分，而不是 `CoreState` 的替代物

### 7. Effect Boundary Layer

长期上需要一个明确的 effect boundary：

- `EventTrace` 表达原生流程中已经发生、可观察的事
- `ProposedEffects` 表达 overlay 层建议发生的事
- `EffectApplier` 负责检查提案是否在当前模式、白名单与边界内

默认模式下，应优先允许：

- `MetaState` 更新
- UI 标记
- 旁白与提示
- 礼崩记录

任何面向 `CoreState` 的写回，都应视为更严格的后续议题。

### 8. Authoring Layer

职责：

- 规则模板
- 文案模板
- 事件标签
- 卡牌/遗物标签
- 是长期内容生产核心

说明：

- 长期来看，内容生产而非引擎代码，会成为工作量主体
- 因此模板组织方式必须比硬编码更可维护

## 默认模式下的代码层与 LLM 层边界

### 纯代码 / deterministic-first

- 状态读取与标准化
- scene 识别
- signal 提取
- 主题打分
- 规则匹配
- 规则选择
- 惩罚结算
- 日志

### 默认模式下优先开放的 LLM control surfaces

- context enrichment
- theme hinting / interpretation assistance
- candidate rule reranking
- bounded penalty modulation（未来但受限）
- 旁白润色
- 礼制解释的文案化理由
- run 结束总结
- reflection / run summarization

### 默认模式下不交给 LLM 决定的部分

- 规则是否生效
- 惩罚数值
- 哪个选项能否点击
- 当前场景有哪些合法动作

原因很简单：在当前 MVP / 默认模式下，这些部分若直接脱离 kernel 的决定论结构，会明显削弱可复现、可调试、可测试的基础，也会让未来 mod 接入阶段的行为验证变得困难。

### 未来可扩展的实验模式

未来可以存在明确标注的实验模式，例如“整活模式”“失序模式”或其他高裁量权导演模式。在这些模式下，LLM 可以被授予更高自由度，例如：

- 决定某条候选规则是否临时生效
- 在预设安全区间内浮动惩罚数值
- 生成临时法令草案
- 加入更混沌、更戏剧化的导演行为

可参考的 mode 思路包括：

- `classic`: kernel 主导，LLM 最少参与
- `ritual`: kernel 主导，LLM 辅助解释、重排、旁白与总结
- `chaos`: 实验模式下开放更高裁量权

但这类模式应同时具备：

- 明确开关
- 安全边界
- 回退机制
- 日志记录
- 与默认模式清楚区分

这不是当前仓库的首要实现目标，只是长期可扩展方向。

## 核心数据结构建议

以下是当前原型适用的核心结构表达。写法接近 dataclass 字段清单，而不是正式代码。

### `RunSnapshot`

```python
@dataclass
class RunSnapshot:
    run_id: str
    act: int
    floor: int
    scene_type: str
    character_id: str
    hp: int
    max_hp: int
    gold: int
    deck_summary: dict[str, int]
    relics: list[str]
    potions: list[str]
    ritual_collapse: int
    active_edicts: list["ActiveEdict"]
    recent_violations: list["ViolationRecord"]
    run_memory: "RunMemory"
```

### `ChoiceContext`

```python
@dataclass
class ChoiceContext:
    scene_type: str
    options: list["ChoiceOption"]
    derived_signals: "DerivedSignals"
```

### `ChoiceOption`

```python
@dataclass
class ChoiceOption:
    option_id: str
    label: str
    option_type: str
    tags: list[str]
    value_hints: dict[str, float | int | str]
```

### `DerivedSignals`

```python
@dataclass
class DerivedSignals:
    hp_ratio: float
    deck_size: int
    attack_count: int
    skill_count: int
    power_count: int
    recent_attack_picks: int
    recent_greedy_choices: int
    next_elite_risk: float
    can_rest_soon: bool
    gold_tight: bool
```

### `RuleTemplate`

```python
@dataclass
class RuleTemplate:
    rule_id: str
    scene_type: str
    themes: list[str]
    priority: int
    trigger: dict
    restriction: dict
    penalty: "PenaltySpec"
    narration_slots: list[str]
    cooldown_floors: int
    max_per_act: int
```

### `ActiveEdict`

```python
@dataclass
class ActiveEdict:
    rule_id: str
    theme: str
    issued_at_floor: int
    expires_at: int | None
    applies_to_option_ids: list[str]
    violated: bool
```

### `ViolationRecord`

```python
@dataclass
class ViolationRecord:
    rule_id: str
    scene_type: str
    floor: int
    option_id: str
    penalty_applied: int
    reason: str
```

### `RunMemory`

```python
@dataclass
class RunMemory:
    ritual_collapse: int
    recent_edicts: list["ActiveEdict"]
    recent_violations: list["ViolationRecord"]
    theme_counters: dict[str, int]
    vows: list[str]
    judge_mood: dict[str, float]
    memory_events: list["MemoryEvent"]
    narrative_summary: "NarrativeSummary | None"
    judge_persona_state: "JudgePersonaState | None"
```

### `MemoryEvent`

```python
@dataclass
class MemoryEvent:
    floor: int
    scene_type: str
    event_type: str
    theme: str | None
    payload: dict[str, str | int | float]
```

### `JudgePersonaState`

```python
@dataclass
class JudgePersonaState:
    current_impression: str
    tone_bias: list[str]
    severity_bias: str
    persona_tags: list[str]
```

### `NarrativeSummary`

```python
@dataclass
class NarrativeSummary:
    short_summary: str
    dominant_themes: list[str]
    behavior_pattern: str
```

### `PenaltySpec`

```python
@dataclass
class PenaltySpec:
    ritual_collapse_delta: int
    warning_only: bool
    future_bias_tags: list[str]
```

这些结构的意义在于：

- 让上下文、规则、结果、记忆彼此解耦
- 让 CLI 样例、测试夹具、未来 mod adapter 使用同一套概念
- 让“旁白层”始终只是读取结构化裁决，而不是自己发明事实

这里保留的是长期结构方向，不要求当前仓库一次性全部实现。当前 MVP 至少需要 `RunMemory`；`JudgePersonaState` 与 `NarrativeSummary` 可作为后续扩展。

## 规则模板组织方式

规则不应散写成硬编码 `if-else`，而应按资源层组织。

一级：场景

- `map`
- `card_reward`
- `shop`
- `relic_reward`
- `event`
- `combat_light`（future only）

二级：主题

- 避争
- 克己
- 谦退
- 守序
- 正名
- 慎独
- 祭备
- 尊卑

三级：具体模板

每条模板至少包含：

- 触发条件
- 限制对象
- 执行方式
- 惩罚
- 文案槽位
- 冷却
- 黑名单条件
- 适合的 run 氛围（可后续扩展）

这样组织的好处：

- 场景维度决定可用规则池，便于筛选
- 主题维度决定风格与解释一致性
- 模板维度承载真正可执行的约束
- 作者可以独立扩内容，而不必频繁改引擎代码
- 更适合做批量测试、统计覆盖率、未来 mod UI 标注

## 主题与规则的映射策略

不建议做“先主题、后规则”的僵硬单向流程，而应采用双向打分：

1. 先根据局势给主题打分
2. 再筛当前场景可用规则
3. 规则本身也带有 `theme` 权重与场景适配信息
4. 最终综合：

`总分 = 主题匹配分 + 场景适配分 + 当前风险分 + 新鲜度分 - 重复惩罚 - 冲突惩罚`

这样做的目的：

- 避免系统总是机械地重复同一种主题
- 避免主题层一旦误判就把规则选择完全锁死
- 允许“当前风险更高但主题略弱”的规则上位
- 为未来引入冷却、重复衰减、run 风格偏置预留空间

## 当前阶段目标（Python 原型阶段）

### MVP 目标

做一个 **战斗外决策裁判系统的离线原型**，优先通过 CLI 或可回放 demo 验证玩法。

### MVP 必须包含

- 4 类场景：
  - 地图选路
  - 卡牌奖励
  - 商店
  - 事件
- 1 个全局状态：
  - `ritual_collapse` / 礼崩值
- 1 个轻量记忆层：
  - recent violations
  - recent edicts
  - basic theme counters
  - optional judge mood values
- 最小主题集：
  - 避争
  - 克己
  - 谦退
  - 守序
  - 慎独
  - 正名
- 一批规则模板（建议 15~20 条）
- 一套旁白模板系统
- 守礼 / 违礼 / 累计礼崩 / run log
- 轻量 run memory 更新

### 第一版明确不做

- AI 自动战斗
- 复杂战斗内限制
- 全卡池深度语义理解
- 全事件覆盖
- 自由生成规则
- 重度 agent planning
- 联网强依赖
- 真正 mod API 深度接入
- UI 复杂工程化
- 完整 LLM persona memory
- 长对话式记忆代理
- 每一步都调用 LLM 总结整局

这些约束与 `mvp-scope.md` 保持一致。本文不重复维护更细的当前执行清单，细节以现有 MVP 文档为准。

## 从 Python demo 到未来 mod 的阶段路线

### Phase 1: Python 离线原型

- sample contexts
- rule engine
- narration templates
- CLI/demo
- tests
- 轻量 structured run memory

目标：确认核心玩法方向是否成立。

### Phase 2: 内容扩展与试玩

- 扩规则
- 扩样例
- 调惩罚曲线
- 调重复度
- 调文案风格
- 调整记忆如何影响法令与语气

目标：确认系统在更大样本上是否仍然稳定且有趣。

### Phase 3: 只读式真实游戏接入验证

- 尝试从真实游戏中导出 `choice context`
- 不干预，只观察
- 验证数据结构是否足够

目标：先验证输入协议，而不是立刻接管游戏流程。

### Phase 4: 轻量 mod 干预

- 地图 / 卡牌奖励两个场景先接
- 高亮违礼
- 二次确认
- 游戏内 `ritual_collapse`

目标：只做轻干预，验证玩家是否愿意接受游戏内礼官存在。

### Phase 5: 可选 LLM 润色与更强导演化

- 旁白润色
- run 总结
- 风格记忆增强
- 更复杂的长期导演系统
- 可选 LLM judge memory / persona memory

目标：在不破坏决定论骨架的前提下，提高导演人格与连续叙事感。

路线顺序必须保持：

- 先 demo
- 再只读接入
- 再轻干预
- 再正式 mod 化

不要反过来。这是项目推进顺序，而不是版本营销路线。

## 规则模板样例（设计保留）

以下样例保留为设计方向参考，便于未来扩充模板库。它们不是当前 repo 中已经全部落地的实现列表，也不与当前 `data/rules/` 中的小型示例库强行一一对应。

### 地图

#### M1 避争：低血量时近程精英路径违礼

- 触发条件：`hp_ratio` 低，且近两层内存在精英路径
- 限制：不得主动选择近程精英路线
- 惩罚：违礼则 `ritual_collapse +2`
- 示例旁白：此时血气未定，不宜先赴强敌座前。

#### M2 守序：连续三次未知节点违礼

- 触发条件：近期路径连续偏向未知节点
- 限制：当前再选未知节点视为违礼
- 惩罚：违礼则 `ritual_collapse +1`
- 示例旁白：道路既分而次序未立，不可再任意投身于未明之处。

#### M3 祭备：临近 boss 却不走准备路径违礼

- 触发条件：接近 boss，且可见休息点、商店或稳妥准备路径
- 限制：若放弃准备而直趋高压节点，则违礼
- 惩罚：违礼则 `ritual_collapse +2`
- 示例旁白：大礼将临，当先备器整冠，不可空手趋殿。

### 卡牌奖励

#### C1 克己：连续拿攻击牌，再拿攻击违礼

- 触发条件：最近数次奖励连续偏向攻击牌
- 限制：当前继续拿攻击牌视为违礼
- 惩罚：违礼则 `ritual_collapse +1`
- 示例旁白：偏锋既盛，当知自抑，不可再纵其势。

#### C2 避争：低血量时拿高攻击牌违礼

- 触发条件：血量低，且奖励中存在明显高攻高风险选项
- 限制：优先进防御、恢复或跳过；继续取高攻牌违礼
- 惩罚：违礼则 `ritual_collapse +2`
- 示例旁白：身未安而先竞锋名，此举失次。

#### C3 正名：牌组失衡时继续加剧失衡违礼

- 触发条件：牌组攻防结构明显失衡
- 限制：继续加剧单一方向失衡视为违礼
- 惩罚：违礼则 `ritual_collapse +1`
- 示例旁白：名器失其分，今当正其偏，不可再助其歪斜。

### 商店

#### S1 节用：低金币时买高价奢侈品违礼

- 触发条件：金币偏低，且商店中存在高价装饰性或不明价值物
- 限制：购买高价奢侈品视为违礼
- 惩罚：违礼则 `ritual_collapse +2`
- 示例旁白：囊中之数既薄，不可先竞华饰。

#### S2 先本后末：明明该移除冗余牌却先买花哨物违礼

- 触发条件：牌组中冗余牌明显，且商店可进行移除
- 限制：先购买花哨物而不先处理冗余，视为违礼
- 惩罚：违礼则 `ritual_collapse +1`
- 示例旁白：本末未正，岂可先饰其末。

#### S3 守分：单件商品价格过高，倾囊一掷违礼

- 触发条件：单件商品成本接近全部金币
- 限制：倾囊购买视为违礼
- 惩罚：违礼则 `ritual_collapse +1`
- 示例旁白：一物独贵而尽倾所有，此非守分之举。

### 事件

#### E1 慎独：高收益高代价贪婪选项违礼

- 触发条件：事件提供高收益且伴随高代价的明显诱惑项
- 限制：若直接取利而无缓冲条件，则违礼
- 惩罚：违礼则 `ritual_collapse +1`
- 示例旁白：无人监处，尤见其心；此利虽厚，不宜轻取。

#### E2 避祸：低血量时事件冒险分支违礼

- 触发条件：血量低，事件存在受伤或高波动分支
- 限制：冒险分支视为违礼
- 惩罚：违礼则 `ritual_collapse +2`
- 示例旁白：祸机在侧，病身不当先试其险。

#### E3 守信：先前许诺后反悔违礼

- 触发条件：前序事件或 run 记忆中存在承诺状态
- 限制：当前若反悔、背约或自毁先前宣示，视为违礼
- 惩罚：违礼则 `ritual_collapse +2`
- 示例旁白：前言既出，今又翻覆，是为失信。

## 礼官旁白系统设计

目标：

- 风格统一
- 不太重复
- 不脱离可执行规则

当前阶段优先：

- 模板拼接

未来阶段可选：

- LLM 润色

正确顺序必须是：

1. 代码先选规则
2. 生成结构化裁决对象
3. 模板产出基础文案
4. LLM 可选重写

其中，规则对象才是 source of truth。UI 上必须同时显示简明裁决句，不能只显示润色后的长旁白。这一点和现有 README、MVP 文档保持一致。

结构化裁决对象示例：

```json
{
  "theme": "避争",
  "rule_id": "M1_LOW_HP_AVOID_ELITE",
  "scene": "map",
  "observation": "当前生命较低，且可选路径中存在近程精英路线",
  "verdict": "近两层内不得主动取精英路径",
  "penalty": "违礼则礼崩值+2",
  "tone": "serious_absurd"
}
```

在当前默认模式下，LLM 可以改写措辞，但不改 `rule_id`、`verdict`、`penalty`。未来若探索实验模式，也应通过显式策略决定哪些结构字段允许浮动，并由 kernel 负责验证与记录。

## Agent Loop 设计

### Observe

- 输入：样例 JSON 或未来 adapter 导出的游戏状态
- 处理：标准化为 `RunSnapshot`、`ChoiceContext`，并读取当前 `RunMemory`
- 输出：结构统一、字段完整的上下文对象与当前记忆状态

### Interpret

- 输入：`ChoiceContext`
- 处理：结合 `ChoiceContext` 与 `RunMemory`，提取 signals、计算主题分数、识别当前局势的礼制倾向
- 输出：`DerivedSignals`、主题评分结果与记忆相关提示

### Decide

- 输入：signals、主题分数、规则模板库、memory 状态
- 处理：筛选可用规则、处理冲突、排序选出当前法令
- 输出：当前 `ActiveEdict` 或等价的结构化裁决对象

### Act

- 输入：当前法令与候选选项
- 处理：标记守礼/违礼、计算礼崩增量、写入日志、生成基础旁白
- 输出：可展示、可记录、可测试的裁决结果

### Reflect

- 输入：本次裁决结果与玩家选择
- 处理：更新近期违礼记录、主题计数、前科、礼官态度、必要时更新简短叙事摘要
- 输出：更新后的 `RunMemory`，供后续节点读取

当前实现仍可让 `Reflect` 保持轻量，但从架构上它已经是完整系统的重要组成部分，而不是可随意删除的附属步骤。

## 长期开发顺序

### 0. 明确项目定义、MVP、风格边界

- 目标：把项目写清楚，避免误做成自动打牌 AI
- 产出物：定义文档、范围文档、风格文档
- 是否需要 AI：不需要
- 如何验证：文档之间不冲突，团队能复述项目目标

### 1. 定义数据结构与 schema

- 目标：稳定上下文、规则、输出格式
- 产出物：schema、样例 JSON、字段清单
- 是否需要 AI：不需要
- 如何验证：样例可以被解析，字段足以表达 MVP 场景

### 2. 做规则引擎 v0

- 目标：跑通最小筛选、匹配、选择与结算
- 产出物：deterministic rule engine
- 是否需要 AI：不需要
- 如何验证：同一输入产生稳定输出

### 3. 做文本模板系统

- 目标：让结构化裁决能被转成礼官口吻
- 产出物：模板库、旁白生成器
- 是否需要 AI：不需要
- 如何验证：模板输出与规则对象一致

### 4. 做 choice simulator / CLI demo

- 目标：建立可反复演示与调试的离线入口
- 产出物：CLI、样例 runner、snapshot 输出
- 是否需要 AI：不需要
- 如何验证：可以批量跑样例并审查输出

### 5. 人工扩第一批规则内容

- 目标：从几条规则扩到一批可试玩内容
- 产出物：15 到 20 条左右规则模板与样例
- 是否需要 AI：可选，用于整理草案，不用于最终裁决
- 如何验证：覆盖主要场景，重复度可接受

### 6. 只读式游戏接入验证

- 目标：验证真实游戏状态能否映射到现有结构
- 产出物：adapter 草案、导出样本
- 是否需要 AI：不需要
- 如何验证：真实状态可以稳定转为 `ChoiceContext`

### 7. 轻量 mod 干预

- 目标：先在少数场景中做高亮与确认，不急于深介入
- 产出物：地图 / 卡牌奖励的轻量接入原型
- 是否需要 AI：不需要
- 如何验证：玩家能看懂并接受礼官提示

### 8. 可选 LLM 润色

- 目标：提升旁白质感与 run 总结表现
- 产出物：可关闭的润色层
- 是否需要 AI：需要，但为可选层
- 如何验证：润色不改变结构化裁决，只提升表达

### 9. run summary / 更强导演人格

- 目标：让系统具备更连续的“礼官人格”和更完整的节目效果
- 产出物：run 总结、风格记忆、长期偏置
- 是否需要 AI：可选
- 如何验证：连续 run 中人格与规则风格有可识别延续

## 第一周行动清单（初始规划）

以下内容保留为早期规划参考版本。当前执行应以实际 repo 状态为准，此处主要用于保留项目形成过程。

### Day 1

- 项目定义
- 风格边界
- MVP 约束

### Day 2

- 核心数据结构
- schema 草案
- context 字段整理

### Day 3

- 最小规则引擎
- 规则匹配与选择逻辑

### Day 4

- 第一批规则模板
- 场景标签与主题标签

### Day 5

- 最小 demo
- CLI 入口
- 输出 snapshot

### Day 6

- 旁白系统
- 模板清理与风格审查

### Day 7

- 试玩删改
- 调规则密度
- 调礼崩曲线
