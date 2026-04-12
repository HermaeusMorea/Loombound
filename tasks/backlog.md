# Backlog

## Near-Term

- 为 `relic_choice` 增加样例 context
- 增加多阶段 `ritual_collapse` 阈值设计
- 增加“规则为何未被选中”的解释输出
- 增加批量 demo runner
- 增加 snapshot fixture 测试

## Content

- 扩充 `restraint` 主题规则
- 扩充 `order` 与路径选择规则
- 为 shop 增加“重器 / 俗物 / 保命”分类
- 为 event 增加“受试 / 辞让 / 冒进”分类

## Architecture

- 设计 rule conflict handling
- 设计 adapter 层输入协议
- 设计长期 run state 与 event log
- 扩充 read-only observation samples 与 adapter coverage

## Open Design Questions

- 主题分数是否只用于排序，还是要作为启用阈值
- 单节点是否允许主规则 + 附属警示规则
- `ritual_collapse` 是否应按违规类型分桶
- 旁白模板是否应支持按规则单独配置
