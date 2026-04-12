# System Architecture

## Design Goal

构建一个离线、可检查、可调试的外部规则引擎，并以 `Deterministic Kernel + LLM Control Surfaces` 作为长期架构表述。当前默认模式下，kernel 仍是 source of truth、validator 与 fallback；但 LLM 在这个项目中不应只被理解为旁白插件，而应被理解为 `MetaState` 的重要解释者与裁决提议者。

系统长期上应被理解为一个 overlay-style ritual judge：

- 原生游戏拥有 `CoreState`
- 本项目拥有 `MetaState`
- 本项目通过未来 hook points / adapters 观察原生流程
- 本项目不替换原生 run-level 或 encounter-level state machines

## Pipeline

1. `Run`
2. `Node`
3. `Arbitration`
4. `signals`
5. `MetaState interpretation`
6. `rule matching`
7. `rule selection / proposal validation`
8. `enforcement`
9. `optional narration`
10. `node memory update`
11. `run memory update`
12. `run snapshot`

当前 runtime model 应理解为：

- `Run`
  整局对象，持有全局 `CoreState` 视图、`MetaState`、`RunMemory`
- `Node`
  当前地图节点 / 房间对象，持有节点级状态与 `NodeMemory`
- `Arbitration`
  附着在 `Run` 或 `Node` 上的一次待裁决场景

- `ArbitrationContext`
  `Arbitration.context` 的类型，显式携带 `core_state_view` 与 `meta_state_view`
- `Arbitration`
  一次裁决对象本身，拥有 owner、context、result 与状态

## Core Game State Vs. Meta State

### `CoreState`

`CoreState` 指原生游戏拥有的状态。它包括 run-level、encounter-level、资源、节点推进、原生合法动作集合等原生流程事实。

在未来真实接入阶段，本项目默认不拥有 `CoreState`，也不直接替代原生状态机。

### `MetaState`

`MetaState` 指本项目拥有的 overlay 状态。它包括：

- `ritual_collapse`
- structured run memory
- recent edicts
- recent violations
- theme counters
- judge mood values
- future persona-oriented memory fields

在长期设计里，`MetaState` 不只是手工统计层，也是一层礼官视角的解释状态：

- kernel 负责定义其结构边界
- LLM 可以参与提取、归纳、更新其中的解释性字段
- 后续裁决应读取 `MetaState`，而不只读取当前节点原始输入

在下一阶段的数据模型中，可以更明确地区分：

- `Run.core_state` / `Run.meta_state`
- `Node.entered_core_state` / `Node.entered_meta_state`
- `Arbitration.context.core_state_view` / `Arbitration.context.meta_state_view`

这样既能减少每次操作都重新拼接完整上下文，也能让整局资源状态与节点局部状态的关系更清楚。

这也意味着：

- `Run` 持有整局级状态
- `Node` 持有节点进入时继承的状态视图与节点内局部状态
- `Arbitration` 只处理一次待裁决场景，不直接成为全局状态容器

## EventTrace

`EventTrace` 指从原生流程中抽取出的标准化可观察事件。它是未来 adapter 层的核心输出形式，用于让 overlay 系统在不知道底层 API 细节的情况下消费统一事件流。

示意上，`EventTrace` 可覆盖：

- room entered
- combat started
- reward selected
- event branch chosen
- combat ended

## ProposedEffects And EffectApplier

### `ProposedEffects`

`ProposedEffects` 指 overlay 层基于当前 `CoreState` 视图、`MetaState` 和记忆推导出的有界效果提案，例如：

- 标记哪些选项违礼
- 给出礼崩增量建议
- 给出是否显示二次确认的建议
- 给出旁白与警示文案
- 在未来实验模式下给出有限范围内的 `ProposedEffects`

它们是提案，不是直接写回。

### `EffectApplier`

`EffectApplier` 是决定论的 validator / applier。它负责：

- 检查 `ProposedEffects` 是否在当前模式与安全边界内
- 确认哪些内容只更新 `MetaState`
- 在未来接入阶段确认哪些内容可以合法写回原生流程
- 作为 fallback 路径在无 LLM 时独立运行

默认模式下，任何面向 `CoreState` 的写回都应经过 `EffectApplier`。

## LLM Authored JSON Assets

除直接参与 interpretation、MetaState 更新、reranking 或 narration 外，未来还可以让 LLM 以更稳妥的方式参与“内容生产层”。

一个可行路径是：在整局 run 开始前，或在某些局内节点前，由 LLM 预生成受 schema 约束的 JSON assets，例如：

- 临时规则包
- 旁白模板包
- 本局初始礼官 persona / mood 配置
- 未来实验模式下的候选 `ProposedEffects`

这些 JSON assets 不应被视为可直接执行的自由文本指令，而应满足两个条件：

- 结构上可映射到既有 schema、`RuleTemplate` 或其他明确的数据模型
- 执行前仍需经过 deterministic kernel 的加载、校验、筛选与裁决

这意味着 LLM 可以参与“写规则包”“写本局导演素材”，也可以参与生成 `MetaState` 的解释性补充；但默认模式下不直接绕过 rule engine 与 kernel validation。本项目更鼓励：

- 让 LLM 生成结构化候选内容
- 让 kernel 负责决定哪些内容合法、可用、可回放

相较于把 LLM 放在每一步实时自由裁决，这种方式更适合当前仓库的 deterministic-first 原则，也更容易逐步演化到未来的 overlay integration。

## Module Responsibilities

### `models.py`

定义 kernel-visible state、rule、evaluation、snapshot，以及 shared kernel models。

当前 `models.py` 中已经包含：

- `ArbitrationContext`
- `ArbitrationResult`
- `CoreStateView`
- `MetaStateView`
- `NodeSummary`
- `RuleTemplate`
- `RuleEvaluation`
- `OptionResult`
- `NarrationBlock`
- `RunSnapshot`

当前 runtime lifecycle object 已经移入：

- `src/core/runtime/session.py`
  - `Run`
  - `Node`
  - `Arbitration`

当前 memory model 已经移入：

- `src/core/memory/types.py`
  - `NodeMemory`
  - `RunMemory`
  - `NodeEvent`
  - `NodeChoiceRecord`
  - `ViolationRecord`

### `signals.py`

从输入上下文抽取决定论信号，例如：

- 决策类型
- 当前阶段
- 资源压力
- 选项标签
- 是否存在“安全 / 节制 / 高风险 / 贪取”线索

### `theme_scorer.py`

将局势映射到礼制主题分数，例如：

- `order`
- `restraint`
- `avoid_conflict`
- `humility`

### `rule_matcher.py`

判断某条规则是否适用于当前 context，并记录命中原因。

### `rule_selector.py`

在适用规则中做稳定选择。当前实现采用：

- 主题吻合度
- 规则优先级
- `id` 字典序

此外，当前 runtime 已引入两层规则状态：

- `RuleSystem`
  挂在 `Run` 上，记录整局模板集合、最近使用规则与规则使用次数
- `NodeRuleState`
  挂在 `Node` 上，记录当前节点的候选规则、选中规则与 selection trace

当前 selector 已开始轻量读取：

- `RuleSystem.recently_used_rule_ids`
- `RunMemory.theme_counters`

并把它们作为小幅度的决定论偏置，用于：

- 避免同一 rule 过于频繁地连续出现
- 让长期反复出现的主题对后续选择产生轻微影响

这一步仍然保持 deterministic-first：

- 不替代 rule matching
- 不绕过 kernel validation
- 不直接引入自由度过高的策略层
- 只在候选规则之间做轻量排序调整

### `enforcement.py`

依据规则对选项做标记，并给出：

- 守礼/违礼状态
- 原因
- `ritual_collapse_delta`

### `narrator.py`

从模板库中生成可选旁白。旁白是附加层，可关闭；在当前默认模式下，不依赖外部模型作为必需条件。

### `memory.py` or future memory modules

维护 run-scoped memory 与 node-scoped memory，包括结构化事实、最近法令、最近违礼记录、主题计数与礼官态度参数。

这里还应进一步区分：

- `RunMemory`
  整局持续存在
- `NodeMemory`
  节点内持续存在，节点结束后提炼并写回 `RunMemory`

当前 `RunMemory` 已经开始反向影响 rule selection，但仍处于轻量偏置阶段，而不是完整策略控制层。

## Kernel Vs. Control Surfaces

### Deterministic Kernel

当前架构默认采用 deterministic kernel：

- 统一数据结构
- 默认规则流水线
- 惩罚执行
- run memory 读写与结构化记忆维护
- decision trace 与回放
- 对 LLM 输出做验证、裁决与 fallback

这保证了：

- 输出可复现
- 规则可调试
- 惩罚可验证
- 样例与未来游戏接入可对齐

### LLM Integration Surfaces

未来可以扩展明确标注的 LLM control surfaces，例如：

- `State / Context`
  可接 `context enrichment`
- `Signal / Interpretation`
  可接 `theme hinting` 与 `MetaState interpretation`
- `Rule Engine`
  可接 `candidate rule reranking`，以及 future experimental 的 `rule proposal`
- `Enforcement`
  可接 `bounded penalty modulation`
- `Narration`
  可接 LLM narration backend
- `Reflection`
  可接 run summarizer 与 persona evolution

在本项目语境下，最重要的 control surface 之一其实是：

- 基于 `CoreState` 视图、`EventTrace` 与记忆，提取礼官视角的 `MetaState`
- 再由该 `MetaState` 反过来影响 rule proposal、judgement tone 与后续 memory update

## Memory Layer

记忆层不只是日志存放处，而是会反馈进入后续 decision pipeline 的核心层。

### Structured Run Memory

这是 kernel truth，负责保存可执行、可测试、可回放的记忆状态，例如：

- `ritual_collapse`
- recent edicts
- recent violations
- theme counters / theme profile
- vows / promises / standing constraints
- judge mood values，例如严苛、多疑、惩贪、宽赦
- important prior incidents

它直接影响：

- 规则排序
- 惩罚升级
- 场景判断
- 后续法令偏好

### Narrative / Persona Memory

这是未来可选的人格化叙事记忆层，不是唯一真相来源，而是建立在结构化记忆之上的解释层。可包括：

- current impression
- tone bias
- short narrative summary
- future LLM persona state

它更适合影响：

- 旁白连续性
- 礼官人格一致性
- run 总结
- 长线导演感

原则上：

- Structured Run Memory 负责“判什么”
- Persona Memory 负责“怎么判、怎么说、像不像同一个礼官”

### Memory Update Cycle

按当前更准确的时间尺度，应区分两层更新：

### 节点内

1. `Run` 创建或切换当前 `Node`
2. `Node` 在其生命周期内持续维护 `NodeMemory`
3. 当节点内出现一次待裁决场景时，创建 `Arbitration`
4. `Arbitration.context` 读取当前相关的 `CoreState` / `MetaState` 视图
5. 生成裁决结果
6. 节点内的重要结果被记录进 `NodeMemory`

### 节点结束时

1. `NodeMemory` 被提炼成 `NodeSummary`
2. `NodeSummary` 回写到 `RunMemory`
3. `NodeMemory` 被销毁
4. 更新后的 `RunMemory` 进入下一个节点

这意味着：

- 不是每一次玩家选择都直接拥有一个全新的长期记忆对象
- 而是节点内持续维护局部记忆，节点结束时再归档到整局记忆

## Future Overlay Pipeline

在未来真实接入阶段，推荐的 overlay pipeline 如下：

1. player input 进入原生游戏流程
2. native kernel 推进并拥有 `CoreState`
3. hook / adapter 将可观察变化整理为 `EventTrace`
4. overlay kernel 读取 `CoreState` 视图、`MetaState` 与 `EventTrace`
5. overlay 更新 `MetaState`
6. overlay 产生 `ProposedEffects`
7. `EffectApplier` 对提案做决定论校验并应用有界效果
8. 执行 memory update 与 snapshot 记录

这条路径的重点是：

- overlay 系统始终叠加在原生状态机之上
- `CoreState` 写回必须经过决定论验证
- 默认模式下，LLM 不直接拥有 `CoreState` mutation 权限
- LLM 的关键职责是解释事件、更新 `MetaState`、生成裁决提议与 `ProposedEffects`

### Default Mode And Experimental Modes

当前默认模式的要求是：

- 没有 LLM 也能完整运行
- 先保证最小可行与可测试性
- 不提前引入复杂 agent framework
- LLM 不直接变更 `CoreState`

未来可以扩展明确标注的实验模式，例如：

- `classic`: kernel 主导，LLM 最少参与
- `ritual`: kernel 主导，LLM 辅助解释、旁白、重排、总结
- `chaos`: 实验模式下开放更高裁量权

但这些扩展应满足：

- 有模式开关
- 有边界约束
- 有日志记录
- 有回退路径
- 不破坏默认模式的稳定实现

## Data Boundaries

- `data/rules/` 保存规则模板
- `data/text/` 保存旁白模板
- `data/sample_contexts/` 保存样例输入
- `schemas/` 约束 JSON 结构

## Important Architectural Decisions

- 规则与文案分离
- 输入上下文与游戏 API 分离
- 规则执行与最终游戏惩罚分离
- 先做单条规则生效，再讨论多规则叠加
- kernel 作为 source of truth、validator 与 fallback
- memory 是 decision pipeline 的反馈层，而不只是日志
- 原生游戏拥有 `CoreState`，本项目拥有 `MetaState`
- 原生写回应通过 `EffectApplier` 而不是直接由解释层执行
- 默认模式优先稳定内核，实验模式单独扩展 control surfaces

## Deferred Questions

- 一个 context 是否允许多条规则并行生效
- `ritual_collapse` 如何映射为长期后果
- structured run memory 的最小字段集合应该是什么
- judge mood values 采用离散档位还是连续参数
- `EventTrace` 的最小标准化 schema 应该是什么
- 哪些 `ProposedEffects` 永远只作用于 `MetaState`
- 哪些写回路径需要 `EffectApplier` 的显式白名单
- 如何处理例外条款与冲突规则
- 将来与真实游戏状态对接时，哪些字段属于 adapter 层
