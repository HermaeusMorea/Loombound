# Module Progress

## 用途

本文档用于记录当前原型的九个核心模块、各自职责、当前实现进度与下一步缺口。

它不是长期架构文档，也不替代 `docs/system-architecture.md`；它更像一份面向当前仓库状态的任务盘点表。

说明：

- 这里记录的是 `src/core/` 下的九个架构模块
- `src/core/runtime/` 是运行入口层，不单列为九个核心模块之一

## 1. Deterministic Kernel

- 作用：
  提供决定论内核所依赖的核心数据模型与稳定输出结构。
- 当前进度：
  `partial`
- 已落地：
  - `src/core/deterministic_kernel/models.py`
- 当前已实现能力：
  - `Run`
  - `Node`
  - `Arbitration`
  - `ArbitrationContext`
  - `ArbitrationResult`
  - `CoreStateView`
  - `MetaStateView`
  - `NodeMemory`
  - `RunMemory`
  - `NodeSummary`
  - `RuleTemplate`
  - `RuleEvaluation`
  - `OptionResult`
  - `NarrationBlock`
  - `RunSnapshot`
- 当前缺口：
  - 让 `Run / Node / Arbitration` 真正接入 runtime
  - 更完整的 snapshot / trace 模型
  - future validator-facing kernel types

## 2. State Adapter / Context Builder

- 作用：
  把 sample JSON 或未来外部输入整理成统一上下文。
- 当前进度：
  `minimal`
- 已落地：
  - `src/core/state_adapter/context_builder.py`
  - `data/sample_contexts/`
  - `Arbitration.from_dict(...)`
- 当前已实现能力：
  - 从本地 sample JSON 载入 arbitration payload
  - 统一成 `Arbitration`
  - 提供通用 `load_json_asset(...)`
- 当前缺口：
  - 将 sample inputs 装配进 `Run / Node / Arbitration` 模型
  - `CoreState` 只读视图
  - 标准化 `EventTrace`
  - 未来 adapter / hook boundary
  - 多种输入源的 adapter 分层
  - 为 LLM interpretation 提供更明确的输入封装

## 3. Signal Extraction / Interpretation

- 作用：
  从当前 context 提取可复用 signals，并给礼制主题打分。
- 当前进度：
  `implemented_v0`
- 已落地：
  - `src/core/signal_interpretation/signals.py`
  - `src/core/signal_interpretation/theme_scorer.py`
- 当前已实现能力：
  - low hp / low gold / safe / greedy / elite 等基础 signals
  - `order / restraint / avoid_conflict / humility` 四类主题分数
- 当前缺口：
  - 可配置权重
  - 更细的主题集
  - future `context enrichment` / `theme hinting`
  - 更丰富的资源 / 路径 / 奖励 signals
  - 面向 `MetaState` 的解释性提取接口

## 4. Rule Engine

- 作用：
  从规则库中筛选并选择当前法令。
- 当前进度：
  `implemented_v0`
- 已落地：
  - `src/core/rule_engine/rule_matcher.py`
  - `src/core/rule_engine/rule_selector.py`
  - `data/rules/rules.small.json`
- 当前已实现能力：
  - 决策类型匹配
  - context tag 匹配
  - hp / gold 数值阈值匹配
  - 单规则稳定选择
  - 以 theme score + priority + id 做决定论 tie-break
- 当前缺口：
  - cooldown
  - conflict handling
  - multi-rule composition
  - freshness / repetition penalties
  - reranking hook
  - 接受 LLM rule proposal 后的 kernel validation 路径

## 5. Enforcement / Outcome Layer

- 作用：
  把规则落到每个选项上，输出守礼/违礼标记与软惩罚代价。
- 当前进度：
  `implemented_v0`
- 已落地：
  - `src/core/enforcement/enforcement.py`
- 当前已实现能力：
  - `keep_ritual / break_ritual`
  - `collapse_if_taken`
  - `ritual_collapse_delta`
  - 基于 preferred / forbidden tags 的软裁决
- 当前缺口：
  - 选择后真正更新 run memory
  - 区分 warning / soft punishment / future hard lock
  - `ProposedEffects`
  - `EffectApplier`
  - 将裁决结果回写到 `MetaState`

## 6. Narration Layer

- 作用：
  用模板把已决定的裁决包装成礼官口吻。
- 当前进度：
  `implemented_v0`
- 已落地：
  - `src/core/narration/narrator.py`
  - `data/text/narration_templates.json`
- 当前已实现能力：
  - opening / judgement / warning 三段模板输出
  - narration 开关
  - 决定论模板选择与 fallback
- 当前缺口：
  - per-rule override
  - richer placeholders
  - style variation
  - optional LLM rewriting

## 7. Memory Layer

- 作用：
  保存 run-scoped ritual memory，并把记忆反馈进后续裁决。
- 当前进度：
  `implemented_v0`
- 已落地：
  - `src/core/deterministic_kernel/models.py`
  - `src/core/memory/run_memory.py`
- 当前目标结构：
  - `ritual_collapse`
  - recent edicts
  - recent violations
  - theme counters
  - `events`
  - future persona summary
- 当前已实现能力：
  - `RunMemory`
  - `NodeMemory`
  - `update_after_node(...)`
  - `run_memory_to_dict(...)`
- 当前缺口：
  - 更符合 node lifecycle 的 event accumulation
  - 节点结束时的 `NodeSummary -> RunMemory` 提炼逻辑
  - summary / persona hooks
  - 与 enforcement / runtime 串接
  - 让 LLM 参与 `MetaState` 解释和更新

## 8. Authoring Layer

- 作用：
  管理规则模板、文本模板、schema、样例 context，以及未来 LLM authored assets。
- 当前进度：
  `partial`
- 已落地：
  - `src/core/authoring/assets.py`
  - `data/rules/rules.small.json`
  - `data/text/narration_templates.json`
  - `data/sample_contexts/`
  - `schemas/`
  - `docs/llm-authored-assets.md`
- 当前已实现能力：
  - 手写规则库
  - 手写 narration 模板
  - 带说明字段的 sample contexts
  - 将规则 JSON 加载为 `RuleTemplate`
  - 将 narration JSON 加载为模板字典
- 当前缺口：
  - 更完整 schema
  - authoring guide
  - 批量内容扩写流程
  - LLM generated rule/text packs
  - LLM generated `MetaState` / persona config assets

## 9. Overlay Integration Boundary

- 作用：
  为未来真实游戏接入预留清晰边界，而不重写原生状态机。
- 当前进度：
  `scaffold_only`
- 已落地：
  - `src/core/overlay_integration/contracts.py`
- 当前已在文档中明确：
  - `CoreState`
  - `MetaState`
  - `EventTrace`
  - `ProposedEffects`
  - `EffectApplier`
- 当前代码骨架：
  - `EventTrace`
  - `ProposedEffect`
  - `EffectApplier` protocol
  - read-only `ObservedScene -> Arbitration` adapter
  - `src/core/runtime/observe_demo.py`
- 当前缺口：
  - 接口定义
  - validator rules
  - bounded write-back registry
  - hook point categories
  - 与 default mode 的写回边界联动
  - 更多真实场景的 read-only observation mapping

## 现阶段最小主链路

当前真正落地并可运行的核心链路是：

`sample JSON -> state_adapter -> Arbitration -> signals -> theme scoring -> rule matching -> rule selection -> enforcement -> optional narration -> snapshot`

但下一阶段目标应变成：

`Run -> Node -> Arbitration(context) -> judgement pipeline -> NodeMemory -> NodeSummary -> RunMemory`

当前负责把这条链路串起来的入口是：

- `src/core/runtime/cli.py`
- `src/core/runtime/run_memory_demo.py`

## 建议近期推进顺序

1. 先把 `Run / Node / Arbitration` 模型真正接进 runtime
2. 再把 `Memory Layer` 与 `MetaState` 解释链路从 scaffold 接进节点级 update
3. 再扩 `Rule Engine` 与 `Authoring Layer` 的规则库、样例 coverage 与提议校验路径
4. 然后补 runtime 侧的 batch runner / replay-friendly snapshot tooling
5. 最后再细化 `Overlay Integration Boundary` 的 `EventTrace / ProposedEffect / EffectApplier` 接口
