# MVP Scope

## Included Decision Types

- `map_routing`
- `card_reward`
- `shop`
- `relic_choice`
- `event_branch`

## Excluded For MVP

- 战斗内出牌与敌我状态求解
- 真正的游戏内 UI 覆写
- 存档整合与跨 run 长期 meta
- debuff、硬锁、强制改写选项
- LLM 在线生成规则

## MVP Behavior

### Required

- 输入一个结构化上下文
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

第一版不做：

- 禁止点击
- 替玩家自动选择
- 直接修改资源、伤害、卡组等数值

## MVP Completion Checklist

- 至少 4 个样例 context
- 至少 3 条规则模板
- 至少 1 条从输入到输出的 CLI 路径
- 至少 2 个基础测试
- 至少 1 版可讨论的文档集

