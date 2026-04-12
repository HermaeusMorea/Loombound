# LLM Authored Assets

## 文档目的

本文档用于约束一类未来可选能力：让 LLM 生成受 schema 约束的结构化 assets，再由 deterministic kernel 决定是否采用。

它不改变当前仓库的默认方向：

- 当前仍以 Python offline prototype 为主
- 当前仍以 deterministic-first 为主
- 当前默认模式下，LLM 不是核心裁决器
- 当前 MVP 仍只覆盖战斗外决策

## 适用场景

LLM authored assets 更适合放在“内容生产层”，而不是直接替代每一步的实时裁决。

建议的使用时机包括：

- run 开始前，生成本局专属规则包
- run 开始前，生成本局旁白模板包
- run 开始前，生成初始礼官 persona / mood 配置
- 某些局内节点前，生成临时规则候选或补充 narration assets
- 未来实验模式下，生成候选 `ProposedEffects`

## 当前建议生成的资产类型

### 1. Rule Pack

结构化规则包，可映射到既有 `RuleTemplate` 或未来扩展版 rule schema。

用途：

- 本局定制礼官风格
- 引入有限数量的临时法令
- 扩大规则覆盖面而不改变 kernel

### 2. Narration Pack

结构化旁白模板包，用于补充 opening / judgement / warning 文案。

用途：

- 本局口吻差异化
- 同主题不同措辞
- 与 judge mood 或 persona state 对齐

### 3. Persona / Mood Config

本局礼官的初始人格与语气配置，可映射到 `MetaState` 或未来 `JudgePersonaState`。

用途：

- 控制礼官的严苛、多疑、惩贪、宽赦等偏向
- 让同一套 kernel 在不同 run 中表现出不同气质

### 4. ProposedEffects Draft

未来实验模式下，LLM 可生成候选 `ProposedEffects` 草案。

用途：

- 提出二次确认建议
- 提出 bounded penalty modulation
- 提出更戏剧化但仍受边界约束的演出效果

默认模式下，这类草案不应绕过 deterministic validation。

## 必须满足的边界

所有 LLM authored assets 都应满足以下要求：

### 结构可验证

- 必须能映射到既有 schema 或明确的数据结构
- 不接受只靠自然语言描述、无法程序化校验的自由指令

### 执行前可校验

- kernel 必须能检查字段是否合法
- kernel 必须能过滤未知字段、越界值、未注册 effect id
- kernel 必须能拒绝不符合当前 mode 的资产

### 默认模式下不直接改写 `CoreState`

- LLM 可以解释 `EventTrace`
- LLM 可以补充 `MetaState`
- LLM 可以生成候选 `ProposedEffects`
- LLM 默认不直接拥有 `CoreState` mutation 权限

### 可回放、可追踪

- 每次生成的 assets 应可保存
- 应能关联到 run、context、mode 与生成时机
- 应能在回放时复用同一份结构化输入

## Kernel 验收流程

建议的默认流程如下：

1. LLM 生成结构化 assets
2. loader 将其读入统一数据结构
3. validator 检查 schema、字段边界与 mode 约束
4. kernel 决定哪些 assets 可进入规则匹配、旁白生成或 `ProposedEffects` 管线
5. 若涉及写回原生流程，仍需经 `EffectApplier`
6. 记录 decision trace、asset version 与结果

这意味着：

- LLM 负责提出候选内容
- kernel 负责裁决内容是否生效
- `EffectApplier` 负责未来 hook-based 的合法写回

## 推荐的最小 JSON 约束

### Rule Pack

- 规则 `id` 必须稳定
- `decision_type` 必须属于已支持场景
- 触发条件必须是结构化字段
- 惩罚必须落在当前允许边界内

### Narration Pack

- 模板 key 必须稳定
- 文案只负责表达，不得覆盖规则结论
- 文案冲突时，以 kernel 裁决结果为准

### Persona / Mood Config

- 只写入允许的 mood / persona 字段
- 数值边界可由 validator 固定
- 不得隐式引入新的 CoreState 事实

### ProposedEffects Draft

- 必须映射到预定义 effect id 或允许的 effect type
- 必须写明作用范围、持续时间与数值边界
- 不允许自由文本直接代表写回动作

## 不建议的做法

- 让 LLM 直接输出一段自由文本，然后系统临场解释为规则
- 让 LLM 在默认模式下直接修改 `CoreState`
- 让 LLM 绕过 rule engine 或 `EffectApplier`
- 把每一步裁决都强制变成一次在线生成

## 与现有文档的关系

- `system-architecture.md` 负责说明 LLM authored assets 在整体架构中的位置
- `master-plan.md` 负责说明这条路径为什么适合长期演化
- 本文档只负责界定：哪些资产可以由 LLM 生成、边界是什么、kernel 如何验收
