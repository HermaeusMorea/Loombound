# System Architecture

## Design Goal

构建一个离线、可检查、可调试的外部规则引擎，并以 `Deterministic Kernel + LLM Control Surfaces` 作为长期架构表述。当前默认模式下，kernel 是第一层判断来源；后续如引入 LLM，更适合作为逐步开放的 control surfaces，而不是替代内核。

系统长期上应被理解为一个 overlay-style ritual judge：

- 原生游戏拥有 `CoreState`
- 本项目拥有 `MetaState`
- 本项目通过未来 hook points / adapters 观察原生流程
- 本项目不替换原生 run-level 或 encounter-level state machines

## Pipeline

1. `choice context`
2. `run memory`
3. `signals`
4. `theme scoring`
5. `rule matching`
6. `rule selection`
7. `enforcement`
8. `optional narration`
9. `memory update`
10. `run snapshot`

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

除直接参与 interpretation、reranking 或 narration 外，未来还可以让 LLM 以更稳妥的方式参与“内容生产层”。

一个可行路径是：在整局 run 开始前，或在某些局内节点前，由 LLM 预生成受 schema 约束的 JSON assets，例如：

- 临时规则包
- 旁白模板包
- 本局初始礼官 persona / mood 配置
- 未来实验模式下的候选 `ProposedEffects`

这些 JSON assets 不应被视为可直接执行的自由文本指令，而应满足两个条件：

- 结构上可映射到既有 schema、`RuleTemplate` 或其他明确的数据模型
- 执行前仍需经过 deterministic kernel 的加载、校验、筛选与裁决

这意味着 LLM 可以参与“写规则包”或“写本局导演素材”，但默认模式下不直接取代 rule engine。本项目更鼓励：

- 让 LLM 生成结构化候选内容
- 让 kernel 负责决定哪些内容合法、可用、可回放

相较于把 LLM 放在每一步实时自由裁决，这种方式更适合当前仓库的 deterministic-first 原则，也更容易逐步演化到未来的 overlay integration。

## Module Responsibilities

### `models.py`

定义 context、rule、evaluation、snapshot 等核心数据结构。

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

在适用规则中做稳定选择。第一版采用：

- 主题吻合度
- 规则优先级
- `id` 字典序

### `enforcement.py`

依据规则对选项做标记，并给出：

- 守礼/违礼状态
- 原因
- `ritual_collapse_delta`

### `narrator.py`

从模板库中生成可选旁白。旁白是附加层，可关闭；在当前默认模式下，不依赖外部模型作为必需条件。

### `memory.py` or future memory modules

维护 run-scoped memory，包括结构化事实、最近法令、最近违礼记录、主题计数与礼官态度参数。当前仓库尚未完整实现这一层，但架构上应明确为核心组成部分。

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
  可接 `theme hinting`
- `Rule Engine`
  可接 `candidate rule reranking`，以及 future experimental 的 `rule proposal`
- `Enforcement`
  可接 `bounded penalty modulation`
- `Narration`
  可接 LLM narration backend
- `Reflection`
  可接 run summarizer 与 persona evolution

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

每次决策节点结束后，系统不仅要输出裁决，还要在玩家选择后更新记忆：

1. 当前局势进入系统
2. 系统读取 `run memory`
3. 生成裁决
4. 玩家选择守礼或违礼
5. 系统记录本次行为
6. 更新 `ritual_collapse`、主题计数、前科与礼官态度
7. 必要时更新简短叙事摘要
8. 更新后的记忆进入后续节点

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
- LLM 更适合解释事件、更新 `MetaState`、生成 `ProposedEffects`

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
