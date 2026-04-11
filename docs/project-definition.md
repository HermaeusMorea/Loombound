# Project Definition

## Working Title

`li-director-sts2`

## Problem Statement

本项目尝试原型化一个“礼官 / 裁判 / 旁白导演”系统。它观察战斗外决策节点，将局势解释为礼制问题，并依据预定义规则对候选选项打上“守礼 / 违礼”标记，同时累积违礼带来的 `ritual_collapse`。

该系统不是自动玩家，也不是战略求解器。它的职责是约束、解释、记录，而不是代替判断。

## Prototype Thesis

若以下三点可以同时成立，则该方向值得继续：

1. 规则模板可以覆盖一批有代表性的战斗外决策节点
2. 规则执行结果能够保持稳定、可调试、可复现
3. 旁白层可以增强主题感，而不破坏规则层的清晰性

## Non-Goals

- 不制作正式 Slay the Spire 2 mod
- 不声明已知任何 STS2 未来 API 或数据结构
- 不实现战斗内出牌 AI
- 不追求平衡性完成度
- 不在第一版引入联网依赖或在线模型调用

## Core Loop Of The Prototype

1. 读取一个外部 `choice context`
2. 提取语义信号与主题分数
3. 匹配可用规则模板
4. 选择一条当前生效规则
5. 对选项执行守礼/违礼标记
6. 生成可选旁白
7. 输出 `run snapshot` 供审查与调试

## Success Criteria For MVP

- 能对 map / card reward / shop / relic / event 中至少 4 类上下文运行
- 能从小型规则库中稳定选出 1 条规则
- 能输出选项标记、违礼记录与 `ritual_collapse` 增量
- 能保存足够的中间信息，方便人工 debug

