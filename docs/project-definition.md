# Project Definition

## Working Title

`li-director-sts2`

## Problem Statement

本项目尝试原型化一个“礼官 / 裁判 / 旁白导演”系统。它观察战斗外决策节点，将局势解释为礼制问题，并依据预定义规则对候选选项打上“守礼 / 违礼”标记，同时累积违礼带来的 `ritual_collapse`。

该系统不是自动玩家，也不是战略求解器。它的职责是约束、解释、记录，而不是代替判断。

更准确地说，该系统不应只被理解为单次节点上的即时裁判，而应被理解为一个 **run-scoped ritual judge**：它会在整局爬塔过程中持续观察并记录玩家行为，在后续节点中根据前科、主题倾向与当前礼官态度调整法令、惩罚与语气。

## State Boundary

本项目不重写原生游戏的 run-level / encounter-level state machines。

- 原生游戏拥有 `CoreState`
- 本项目拥有 `MetaState`
- 系统通过标准化的 `EventTrace` 观察原生流程
- 系统基于这些输入生成有界的判断与 `ProposedEffects`
- 未来若需要写回原生流程，结果都应经过决定论边界与校验，而不是依赖 freeform LLM control

因此，本项目的职责不是接管游戏主状态机，而是在其外覆一层可解释、可记忆、可约束的礼官系统。

## Prototype Thesis

若以下三点可以同时成立，则该方向值得继续：

1. 规则模板可以覆盖一批有代表性的战斗外决策节点
2. 规则执行结果能够保持稳定、可调试、可复现
3. 旁白层可以增强主题感，而不破坏规则层的清晰性

当前项目选择 deterministic-first 的默认工程路线，是为了先验证玩法、结构与可执行性；这不等于永久排斥未来更自由的 LLM 模式，而是先把稳定主路径做出来。

长期来看，本项目的目标也不是把 LLM 永久限定为纯文案工具，而是构建一个：
**由稳定内核托底、并允许 LLM 在多个导演节点逐步介入的礼官导演系统。**

换言之，当前仓库的默认实现是 deterministic kernel，长期架构则应理解为 `Deterministic Kernel + LLM Control Surfaces`。

在这个长期目标中，即时裁决只是第一层。更完整的系统应当具备 run 内持续记忆、逐步形成案卷与偏见、并在后续节点中表现出连续人格的能力。

## Non-Goals

- 不制作正式 Slay the Spire 2 mod
- 不声明已知任何 STS2 未来 API 或数据结构
- 不实现战斗内出牌 AI
- 不追求平衡性完成度
- 不在第一版引入联网依赖或在线模型调用
- 不在当前原型阶段把 LLM 作为唯一或必需的核心裁决器

## Core Loop Of The Prototype

1. 读取一个外部 `choice context`
2. 读取当前 `run memory`
3. 提取语义信号与主题分数
4. 匹配可用规则模板
5. 选择一条当前生效规则
6. 对选项执行守礼/违礼标记
7. 生成可选旁白
8. 在玩家选择后更新记忆并输出 `run snapshot`

## Success Criteria For MVP

- 能对 map / card reward / shop / relic / event 中至少 4 类上下文运行
- 能从小型规则库中稳定选出 1 条规则
- 能输出选项标记、违礼记录与 `ritual_collapse` 增量
- 能维护一个轻量、结构化、可测试的 `run memory`
- 能保存足够的中间信息，方便人工 debug
