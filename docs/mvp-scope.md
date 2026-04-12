# MVP Scope

## Included Decision Types

- `map_routing`
- `card_reward`
- `shop`
- `relic_choice`
- `event_branch`

## State Assumption For MVP

在当前 MVP 中，`CoreState` 被视为外部、已结构化的输入事实。

- MVP 不尝试模拟完整的原生 state machine
- MVP 主要验证 judgment logic、`MetaState` 更新、soft punishment 与结构化输出

## Excluded For MVP

- 战斗内出牌与敌我状态求解
- 真正的游戏内 UI 覆写
- 存档整合与跨 run 长期 meta
- debuff、硬锁、强制改写选项
- LLM 作为核心决策器
- 自由生成规则作为默认主路径

## MVP Behavior

### Required

- 输入一个结构化 `Arbitration`
- 读取并更新一个轻量 `RunMemory`
- 输出一个生效规则
- 对每个选项标记 `keep_ritual` 或 `break_ritual`
- 对违礼选项增加 `ritual_collapse`
- 提供可选旁白文本

### Preferred

- 主题评分过程可检查
- 规则选择过程可检查
- 违礼原因可检查

## Soft Punishment Model

第一版只做软惩罚：

- 玩家可以违礼
- 违礼会被记录
- `ritual_collapse` 会增加
- 未来可根据累计值收紧规则或施加 debuff

当前 MVP 应承认“记忆”是系统核心方向，但只实现一个轻量、结构化、可测试的版本，例如：

- `ritual_collapse`
- recent violations
- recent edicts
- basic theme counters
- optional judge mood values

第一版不做：

- 禁止点击
- 替玩家自动选择
- 直接修改资源、伤害、卡组等数值
- 完整 LLM persona memory
- 长对话式记忆
- 每一步都调用 LLM 总结整局

补充说明：

- 当前 MVP 采用 deterministic-first，默认不让 LLM 成为核心裁决层
- 未来实验模式可以探索更高自由度的 LLM 导演行为，但那属于后续扩展，不在当前 MVP 范围内
- 当前 MVP 的重点是验证 `MetaState + judgment pipeline`
- 当前 MVP 不要求真实 `CoreState` 写回，只要求把外部输入转成可验证的判断链路

## 为未来 LLM 集成预留的最小扩展位

当前 MVP 虽不依赖 LLM，但建议从架构上预留以下低成本扩展位：

- 结构化裁决对象，便于未来接 narration rewriting、reranking 或 reflection
- narration backend 替换点
- decision trace / logs，便于记录 LLM 建议与 kernel 裁决结果
- mode 字段，便于未来区分 `classic`、`ritual`、`chaos`
- future hook points，例如 context enrichment、theme hinting、bounded penalty modulation
- `RunMemory` 及相关 memory event 结构
- `EventTrace`、`ProposedEffects`、`EffectApplier` 的命名与接口占位

这些只是最小扩展位，不意味着当前要实现复杂 agent framework。

## MVP Completion Checklist

- 至少 4 个样例 context
- 至少 3 条规则模板
- 至少 1 条从输入到输出的 CLI 路径
- 至少 2 个基础测试
- 至少 1 版可讨论的文档集
