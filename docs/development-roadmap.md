# Development Roadmap

## Phase 0: Repository Foundation

- 明确项目定义、MVP 边界、风格规范
- 搭建最小 Python 包结构
- 固定样例输入、规则模板、输出结构

## Phase 1: Deterministic Offline Prototype

- 扩充 `choice context` 样例
- 增加 10 到 20 条规则模板
- 建立稳定的规则筛选与执行日志
- 用 CLI 批量跑样例并检查输出一致性
- 先形成无记忆或极弱记忆的即时原型

## Phase 2: Kernel Hardening And Hook Points

- 增加 snapshot 回归测试
- 明确 decision trace 结构
- 预留 narration backend、mode 字段与 future hook points
- 确认哪些 LLM control surfaces 值得先开放
- 引入 structured run memory，并让后续裁决受前面行为影响

## Phase 3: Evaluation Harness

- 增加规则覆盖率统计
- 增加冲突规则案例
- 增加调参入口，例如 collapse 权重与主题阈值
- 验证 recent violations、theme counters、judge mood 是否稳定影响后续法令

## Phase 4: Content Expansion

- 扩展 event / relic / shop 细分规则
- 扩展旁白模板与风格变体
- 设计更严格的礼崩阶段机制
- 增加 judge persona summary 的最小版本

## Phase 5: Game Integration Research

- 定义 adapter 层需求
- 梳理真实游戏侧可观察字段
- 讨论何时引入 mod 原型
- 明确 `CoreState` 与 `MetaState` 的边界
- 起草 `EventTrace` 标准化 schema
- 明确未来 hook points 只负责观察原生流，不假定替换原生状态机
- 梳理 `ProposedEffects` 与 `EffectApplier` 的最小接口

## Phase 6: LLM Control Surface Experiments

- 试验 context enrichment 与 theme hinting
- 试验 candidate reranking 与 narration rewriting
- 在安全边界内评估 bounded penalty modulation
- 验证 `classic / ritual / chaos` mode 设计是否合理
- 默认模式下的 LLM 实验优先作用于 `MetaState`、解释层与 `ProposedEffects`，而不是直接变更 `CoreState`
- 再考虑 future LLM memory / persona layer

## Memory Evolution Order

建议的发展顺序是：

1. 无记忆或极弱记忆的即时原型
2. 有结构化记忆的 run-scoped prototype
3. 有人格摘要的礼官系统
4. 可选 LLM judge memory

不要把复杂 LLM memory 提前到 MVP。

## Exit Criteria For Moving Beyond Prototype

- 规则库具备基本覆盖
- 输出快照足够稳定
- 人工 review 认为风格与行为逻辑一致
- 已明确“哪些逻辑必须仍由外部规则引擎负责”
