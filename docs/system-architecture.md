# System Architecture

本文档描述 `black-archive` 当前采用的系统结构。它面向的是一个运行在 CLI 中的文字冒险 / 跑团式叙事游戏，而不是外部游戏 mod。

当前唯一主入口是：

- `python -m src.core.runtime.play_cli`

也就是说，这份架构不是围绕“离线 demo”组织的，而是围绕一个已经可玩的 CLI loop 组织的。

## 1. High-Level Model

系统采用三层主运行时对象：

- `Run`
- `Node`
- `Arbitration`

它们的关系是：

- `Run` 表示整局游戏
- `Run` 包含全局地图推进与全局状态
- 每次进入地图上的一个场景，会创建一个 `Node`
- 每个 `Node` 内可以包含一个或多个 `Arbitration`

这套结构的目标是让：

- 地图推进
- 节点内事件
- 单次选择裁决

三者在代码里有清晰的生命周期边界。

## 2. Run

`Run` 是整局游戏的宿主对象。

它负责：

- 持有整局级 `CoreState`
- 持有整局级 `MetaState`
- 持有 `RunMemory`
- 持有整局级 `RuleSystem`
- 维护当前 `Node`
- 维护 run-level history

`Run` 代表的问题是：

- 这一整局当前到了哪里
- 玩家整体状态如何
- 之前发生过什么
- 当前后续节点应该如何被解释或预载

## 3. Node

`Node` 是地图上的单个节点 / 场景容器。

它负责：

- 代表一个局部场景
- 持有进入该节点时继承来的状态视图
- 持有 `NodeMemory`
- 持有节点级 `NodeRuleState`
- 管理该节点内的一个或多个 `Arbitration`

一个 `Node` 可以是：

- 某个调查地点
- 某场遭遇
- 某次交易
- 某个事件链
- 某段仪式或异象

`Node` 的生命周期是：

1. 从 `Run` 进入
2. 节点内发生一个或多个 `Arbitration`
3. 节点结束时生成 `NodeSummary`
4. 将重要结果写回 `RunMemory`
5. 节点销毁

## 4. Arbitration

`Arbitration` 是系统中的单次裁决单元。

它表示：

- 当前一次需要玩家做选择的事件
- 当前一次需要 kernel 给出结构化判定的场景

每个 `Arbitration` 包含：

- `Arbitration.context`
- options
- selected option
- result
- status

### `Arbitration.context`

`ArbitrationContext` 是 `Arbitration.context` 的类型。

它负责保存：

- scene type
- floor / act
- resources
- tags
- metadata
- `CoreStateView`
- `MetaStateView`

它不是顶层运行时宿主，而是：

- 一次 arbitration 的输入视图对象

## 5. CoreState And MetaState

系统区分两类状态：

### `CoreState`

`CoreState` 是结构化、可验证、决定论更新的状态层。

当前更适合放在这里的内容包括：

- health
- money
- sanity
- inventory tags
- location
- 其他数值性与明确资源状态

这些状态由 kernel 维护。

### `MetaState`

`MetaState` 是解释层与叙事层状态。

当前更适合放在这里的内容包括：

- 重大遭遇
- 创伤
- 执念
- 恐惧偏向
- narrator tone
- 更适合未来由 LLM 解释和整理的文本性状态

这意味着：

- `CoreState` 更偏事实
- `MetaState` 更偏叙事解释

## 6. Memory Model

系统采用双层 memory：

- `RunMemory`
- `NodeMemory`

### `RunMemory`

`RunMemory` 是整局长期记忆。

它跨节点存在，当前负责保存：

- `sanity`
- `recent_rules`
- `recent_shocks`
- `theme_counters`
- `behavior_counters`
- `important_incidents`
- `narrator_mood`

它用于：

- 为后续裁决提供长期上下文
- 为规则系统提供轻量 bias
- 为未来 LLM 预载与世界解释提供摘要

### `NodeMemory`

`NodeMemory` 是节点内短期记忆。

它只在当前节点存在，当前负责保存：

- `events`
- `choices_made`
- `shocks_in_node`
- `sanity_lost_in_node`
- `important_flags`
- `node_summary`

它用于：

- 描述节点内发生过什么
- 记录节点内每次 arbitration 的结果
- 在节点结束时向 `RunMemory` 提炼重要信息

## 7. Rule System

规则系统由三部分构成：

- `RuleTemplate`
- `RuleSystem`
- `NodeRuleState`

### `RuleTemplate`

静态规则模板，定义：

- 规则适用场景
- 主题
- 匹配条件
- 偏好 / 禁止的 option tags
- `sanity_penalty`

### `RuleSystem`

整局级规则系统状态，挂在 `Run` 上。

当前负责：

- 持有 templates
- 记录 recently used rules
- 记录 rule use counts

### `NodeRuleState`

节点级规则状态，挂在 `Node` 上。

当前负责：

- 当前节点可用规则
- 当前 arbitration 候选规则
- 选中的规则
- selection trace

## 8. Deterministic Pipeline

当前一条 arbitration 的决定论主链是：

`Arbitration -> signals -> theme scoring -> rule matching -> rule selection -> enforcement -> narration`

具体步骤：

1. 从 `Arbitration.context` 和 options 提取 signals
2. 将 signals 映射到主题分数
3. 用 `RuleTemplate` 对当前 arbitration 做匹配
4. 通过 `RuleSystem` 与 `RunMemory` 对候选规则做轻量排序
5. 选出一条主规则
6. 对所有 options 给出 `stable / destabilizing` 裁决
7. 计算 `sanity_cost` 与 `sanity_delta`
8. 可选生成 narration

## 9. State Adapter

`state_adapter` 是当前系统的内容入口边界。

它负责：

- 读取 authored JSON assets
- 将外部内容装配为内部运行时对象
- 在未来承接 LLM 动态生成的 rule pack / node pack / arbitration pack

它的意义不是“只是读文件”，而是：

- 把外部内容格式与内部运行时结构隔开
- 保证 kernel 永远处理统一的内部对象，而不是直接处理自由文本或松散 dict

对当前项目来说，这一层尤其重要，因为未来 LLM 更适合生成：

- 节点素材
- arbitration 场景
- narration 细节
- MetaState 补充描述

而这些内容进入 `Run / Node / Arbitration` 之前，都应该先通过 `state_adapter` 正规化。

## 10. Enforcement

`enforcement` 当前负责：

- 将规则落到每个 option
- 生成 `OptionResult`
- 输出：
  - `stable`
  - `destabilizing`
  - `sanity_cost`
  - `sanity_delta`

这一层当前只做软性的状态与文本后果，不做复杂战斗结算或外部写回。

## 11. Presentation Module

`presentation` 当前负责：

- CLI 展示布局
- 顶部 HUD
- 状态面板输出
- arbitration 场景输出
- choice 列表输出
- map 选择输出
- 结算结果输出
- 底部输入提示输出

它的职责不是决定规则或状态变化，而是把已经确定的运行结果渲染成终端中的可读界面。

当前展示层特征包括：

- ANSI 颜色
- 盒状布局
- 双栏 HUD 页面
- 窄终端自动切换为上下堆叠布局

当前核心文件有：

- `src/core/presentation/cli.py`

## 12. Runtime Module

`runtime` 是当前仓库的运行时胶水层。

它负责：

- `Run / Node / Arbitration` 生命周期
- CLI gameplay loop
- campaign flow and map progression

当前核心入口有：

- `src/core/runtime/play_cli.py`
- `src/core/runtime/campaign.py`

## 13. Authoring And LLM Role

`authoring` 负责：

- 规则 JSON
- narration templates
- arbitrations
- nodes
- campaigns

LLM 当前不直接替代 kernel。

更合适的位置是：

- 在局前或节点前预载未来内容
- 根据 `RunMemory` 预生成下几个节点的信息
- 预生成 node 内每次 `Arbitration` 的具体事件素材
- 在裁决已经确定后，为每次 arbitration 生成文字演出
- 未来帮助整理 `MetaState`

这意味着：

- kernel 管结构、规则、合法状态更新
- LLM 管细节、氛围、文本表现、未来节点预载

## 14. Current Scope

当前仓库的重点不是外部 API 接入，而是：

- 先把 CLI 跑团 loop 做稳
- 先把 `Run / Node / Arbitration` 做成可玩的运行时结构
- 先让 memory、rule system、narration 与 authoring 协同工作

当前真正落地并可运行的主链路是：

`authored JSON -> state_adapter -> Run -> Node -> Arbitration -> deterministic pipeline -> NodeMemory -> RunMemory`

下一阶段则应继续朝这些方向推进：

- 完整地图推进 loop
- 更丰富的 node 类型
- 更明确的 `CoreState / MetaState` 边界
- 更深的 `RunMemory` 反馈
- LLM 预载与叙事演出整合
