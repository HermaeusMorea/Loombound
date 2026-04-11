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

## Phase 2: Evaluation Harness

- 增加 snapshot 回归测试
- 增加规则覆盖率统计
- 增加冲突规则案例
- 增加调参入口，例如 collapse 权重与主题阈值

## Phase 3: Content Expansion

- 扩展 event / relic / shop 细分规则
- 扩展旁白模板与风格变体
- 设计更严格的礼崩阶段机制

## Phase 4: Game Integration Research

- 定义 adapter 层需求
- 梳理真实游戏侧可观察字段
- 讨论何时引入 mod 原型

## Exit Criteria For Moving Beyond Prototype

- 规则库具备基本覆盖
- 输出快照足够稳定
- 人工 review 认为风格与行为逻辑一致
- 已明确“哪些逻辑必须仍由外部规则引擎负责”

