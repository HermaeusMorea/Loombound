# Master Plan

## 文档定位

本文档用于保存 `li-director-sts2` 的长期蓝图，但必须与当前仓库的实现方式保持一致。

它的角色不是重复 `project-definition.md`、`system-architecture.md` 或 `tasks/module-progress.md`，而是回答三件事：

- 这个项目长期想成为什么
- 当前九个核心模块如何朝那个方向演化
- 哪些能力是当前原型已落地，哪些只是下一阶段的明确目标

分工如下：

- `project-definition.md`
  当前项目定义、问题陈述与原型命题
- `system-architecture.md`
  当前系统的架构边界、状态边界与控制面
- `tasks/module-progress.md`
  当前九个模块的实现进度与缺口
- `master-plan.md`
  基于当前架构的长期演化蓝图

## 项目一句话定义

这是一个面向《杀戮尖塔 2》方向的 **overlay-style ritual judge** 原型：

- 它不替玩家打牌
- 它不替代原生状态机
- 它在关键决策节点上，以礼官身份解释局势、施加规则、记录违礼，并逐步形成 run 内记忆

长期上，这不是一个“单点旁白器”，而是一个 **run-scoped ritual judge with memory**。

## 当前总体立场

当前仓库的总体立场应保持稳定，不因长期愿景而混乱：

- Python offline prototype first
- deterministic-first
- out-of-combat MVP first
- LLM is important, but bounded by kernel validation
- native game owns `CoreState`
- this project owns `MetaState`
- future write-back must pass deterministic validation

这意味着：

- 当前仓库不是正式 mod 仓库
- 当前仓库不是自动打牌 AI
- 当前仓库不是实时 LLM autonomous agent
- 当前仓库的核心价值，是先把“LLM 解释 `MetaState` + kernel 验证执行”的礼官系统做成稳定、可检查、可回放的外部原型

## Native Flow And Overlay Position

这个项目未来若接入真实游戏，应被理解为叠加在原生流程之上的 overlay 系统，而不是替代原生流程的“第二状态机”。

边界如下：

- 原生游戏推进 run-level 与 encounter-level state machines
- 原生游戏拥有 `CoreState`
- 本项目维护 `MetaState`
- 本项目通过未来 adapter / hook points 观察原生变化
- 这些变化在 overlay 层中被表示为 `EventTrace`
- overlay 层输出有界的 `ProposedEffects`
- 若未来需要写回原生流程，必须通过 `EffectApplier`

这个边界是整个长期设计的前提。即使未来引入更强的导演能力，也不改变这点。

## 当前已成立的最小主链路

当前仓库真正已经跑通的，是一条离线、决定论、单节点裁决链路：

`sample JSON -> state_adapter -> Arbitration -> signals -> theme scoring -> rule matching -> rule selection -> enforcement -> optional narration -> snapshot`

当前入口：

- `src/core/runtime/cli.py`

当前这条链路已经能验证：

- 样例输入能否被整理成稳定上下文
- 规则库能否在给定 context 下稳定选出一条法令
- 选项是否能被标为 `keep_ritual / break_ritual`
- 是否能给出 `ritual_collapse_delta`
- 是否能输出可选 narration

这条主链路是后续一切扩展的地基。

但从长期设计意图看，这条链路还缺少一个关键步骤：

`signals / EventTrace / run memory -> MetaState interpretation -> rule proposal -> kernel validation`

也就是说，当前代码已经有“规则执行链路”，但还没有真正落地“LLM 解释并构建礼官视角状态层”的部分。

## 九个核心模块

长期演化应继续围绕当前 `src/core/` 下的九个模块组织，而不是脱离现有仓库结构另起一套抽象。

### 1. `deterministic_kernel`

职责：

- 保存核心数据模型
- 提供稳定的输入、规则、结果与 snapshot 结构
- 作为 source of truth、validator 与 fallback 的基础层

当前状态：

- 已有 `Run`、`Node`、`Arbitration`、`RuleTemplate`、`RuleEvaluation`、`OptionResult`、`RunSnapshot`
- 已有 `NodeMemory` / `RunMemory`
- 还没有完整的 replay / trace 模型

长期目标：

- 扩展 kernel-visible state types
- 为 memory、validation、future overlay integration 提供统一数据边界

### 2. `state_adapter`

职责：

- 把 sample JSON 或未来外部输入转成统一上下文
- 隔离外部输入格式与内部规则系统

当前状态：

- 已能从 sample JSON 构造 `Arbitration`
- 仍是离线输入路径

长期目标：

- 引入 `CoreState` 只读视图
- 引入 `EventTrace`
- 形成明确的 adapter / hook boundary

### 3. `signal_interpretation`

职责：

- 提取可复用 signals
- 生成主题分数
- 作为解释层而不是文案层

当前状态：

- 已有基础 signals 与四个主题分数

长期目标：

- 扩更细主题集
- 支持可配置权重
- 预留 `context enrichment` 与 `theme hinting`

### 4. `rule_engine`

职责：

- 从规则库里筛当前可执行规则
- 稳定选出当前法令

当前状态：

- 已有 deterministic matching 与 single-rule selection

长期目标：

- cooldown
- repetition handling
- conflict handling
- multi-rule composition
- future reranking surfaces

### 5. `enforcement`

职责：

- 把规则落到选项层
- 输出软裁决与 ritual 后果

当前状态：

- 已能输出 `keep_ritual / break_ritual`
- 已能输出 `collapse_if_taken` 与 `ritual_collapse_delta`

长期目标：

- 接入 post-choice memory update
- 与 `ProposedEffects` / `EffectApplier` 对齐
- 为 future bounded write-back 准备边界

### 6. `narration`

职责：

- 将已决定的裁决包装成礼官口吻

当前状态：

- 已有模板 narration
- narration 可开关

长期目标：

- per-rule overrides
- richer placeholders
- stylistic variation
- optional LLM rewriting

### 7. `memory`

职责：

- 保存 run-scoped ritual memory
- 让过去行为反馈进后续裁决

当前状态：

- 已有 `RunMemory` / `NodeMemory` 核心类型
- 已有最小 `update_after_node(...)`
- 仍未真正按完整 node lifecycle 接入

长期目标：

- 让 `RunMemory` 成为真正的 `MetaState` 核心
- 建立 post-choice update cycle
- 区分 structured memory 与 persona memory

这也是 LLM 真正发挥价值的主要落点之一：不是替代 kernel，而是帮助把 run history 解释为礼官可用的案卷与态度。

### 8. `authoring`

职责：

- 管理规则、文案、样例、schema 与 future LLM-authored assets

当前状态：

- 已能加载规则与 narration JSON
- 已有 sample contexts、schemas、`llm-authored-assets.md`

长期目标：

- authoring guide
- 更完整 schema
- 更成熟的规则与文案生成流程
- future LLM-authored rule / text packs

### 9. `overlay_integration`

职责：

- 为未来真实游戏接入定义边界
- 隔离 `EventTrace`、`ProposedEffects`、`EffectApplier`

当前状态：

- 只有合同式 scaffold

长期目标：

- 明确 validator rules
- 明确 bounded write-back registry
- 明确 hook point categories

## 当前最关键的缺口

从当前实现状态看，最关键的缺口不是“再写更多抽象”，而是让系统从单次裁决器升级成真正的 run-scoped judge。

最重要的缺口有三个：

### 1. `memory` 还没接进主链路

文档已经把 memory 视为核心层，但当前运行链路仍然主要停留在“单节点裁决 + snapshot 输出”。

这意味着：

- 礼官还不会真正记住玩家前科
- 惩罚还没有随累犯升级
- 后续法令还不会受历史行为影响

### 2. `MetaState` 还没有被真正解释出来

当前仓库已经有 `MetaState` 的文档边界，也已经有 `RunMemory` / `NodeMemory` 类型，但还没有真正把以下过程做出来：

- 从 `CoreState` 视图、`EventTrace`、signals 与 run history 中提取礼官视角解释
- 把这些解释沉淀进可用的 `MetaState`
- 再把 `MetaState` 喂回裁决提议阶段

如果这个环节不成立，LLM 就只能停留在旁白或外围辅助层，无法体现你当前设计里“LLM 是礼官解释器”的核心价值。

### 3. `rule_engine` 还是 v0

当前 rule engine 已经够做 demo，但仍然是：

- 单规则
- 无 cooldown
- 无 repetition penalty
- 无冲突消解

这足以证明概念，但还不足以支撑更长的 run 内制度感。

### 4. `overlay_integration` 仍然只有架构边界

这本身没有问题，因为当前阶段本就不应该急着接真实游戏。

但长期上必须保持三点清醒：

- `CoreState` 不是本项目拥有的
- `MetaState` 才是本项目真正的状态层
- future write-back 不是自由改写，而是 bounded、validated、hook-based

## 记忆型礼官系统的长期目标

长期上，系统要从“在每个节点做一次裁决”演化成“在整局 run 中持续形成案卷”。

这个目标的关键，不只是 memory 进入主链路，还包括让 LLM 参与把记忆和事件解释成真正可用的 `MetaState`。

应该形成的循环是：

1. 读取当前 context
2. 读取当前 `RunMemory`
3. 结合 signals、事件与既有记忆形成 `MetaState`
4. 基于 `MetaState` 匹配、提议并验证规则
5. 输出当前节点裁决
6. 在玩家作出选择后更新 memory 与 `MetaState`
7. 让更新后的状态影响下一个节点

只有这样，礼官才不会表现得像“每步失忆”。

## Structured Memory Vs. Persona Memory

未来的记忆层必须继续坚持两层区分：

### Structured Run Memory

这是执行基础，属于 kernel-truth / `MetaState` 的一部分。

它负责：

- `ritual_collapse`
- recent edicts
- recent violations
- theme counters
- mood-like structured values
- important incidents

它决定“判什么”。

### Persona Memory

这是未来可选的叙事放大器。

它负责：

- 礼官对玩家的当前印象
- 语气偏差
- 简短 run 摘要
- future persona continuity

它决定“怎么判、怎么说”。

默认模式下，不应把 LLM 当作唯一记忆载体。结构化记忆必须先成立。

## Deterministic Kernel + LLM Control Surfaces

这个长期表述依然成立，但要和当前实现进度对齐理解。

当前默认模式下：

- kernel 主导
- 无 LLM 也能跑完整 demo
- rule engine、enforcement、snapshot 都应决定论可复现

但从长期角色分工上说，LLM 不只是 narration addon，而是：

- `MetaState` interpreter
- ritual judgement proposer
- persona / memory shaper

未来可逐步开放的 control surfaces 包括：

- `context enrichment`
- `theme hinting`
- `candidate rule reranking`
- `bounded penalty modulation`
- `narration rewriting`
- `reflection / run summarization`

这些控制面都应建立在 kernel 之上，而不是绕过 kernel。

## LLM 参与内容生产的合理路径

结合当前实现，LLM 更合理的近中期接入方式，不是“替代主链路做实时自由裁决”，而是进入 `authoring` 层。

更具体地说：

- 局前生成规则包
- 局前生成 narration 模板包
- 局前生成初始 persona / mood config
- 局中生成受约束的候选 `ProposedEffects`
- 局中根据事件和记忆更新礼官视角的 `MetaState`

这些产物都应是结构化 assets，而不是自由文本命令。

执行原则仍然是：

- LLM can propose
- kernel must validate / arbitrate
- `EffectApplier` handles future verified write-back

## 从当前原型到下一阶段的顺序

长期路线应继续尊重当前仓库的收敛感，不要反过来被未来 integration 拉着走。

建议顺序：

1. 把 `memory` 从 scaffold 接进主链路
2. 扩 `rule_engine` 与 `authoring` 的规则覆盖和样例覆盖
3. 增加 batch runner / replay-friendly snapshot tooling
4. 再设计更明确的 `overlay_integration` contract
5. 最后才考虑更深的游戏接入与更高自由度的 LLM surfaces

这条顺序本质上是在保护当前 repo 的核心原则：

- 先做 deterministic prototype
- 先把 run-scoped judge 做成立
- 再谈更深的 overlay integration

## 当前最值得继续做的事

如果只选一件事，当前最值得推进的是：

**把 `memory` 与 `MetaState interpretation` 一起接入当前主链路。**

原因很简单：

- 这最能让系统从“即时裁决器”变成“记忆型礼官系统”
- 这最符合 `project-definition.md` 与 `system-architecture.md`
- 这也最能让后续 `rule_engine`、`narration`、`LLM control surfaces` 有真正的长期依附点

在那之后，再扩规则库与 authoring 能力，收益会更高。
