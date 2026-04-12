# 待办清单

## 近期

- 为 `omens_choice` 与 `market_offer` 增加更多样例 arbitration
- 增加多阶段 `sanity` / pressure 阈值设计
- 增加“规则为何未被选中”的解释输出
- 增加批量 campaign runner
- 增加 snapshot fixture 测试
- 打磨 CLI HUD 的信息密度与窄终端表现
- 评估是否要做 `textual` 版真正固定 HUD
- 设计并实现 `llm_interface`
- 让 LLM 开始生成 node / arbitration / narration 资产

## 内容

- 扩充 `composure` 主题规则
- 扩充 `clarity` 与 `self_preservation` 规则
- 为 `night_market` 增加“补给 / 诱物 / 离场”分类
- 为 `omens` 场景增加“试探 / 克制 / 退避”分类

## 架构

- 设计 rule conflict handling
- 设计 adapter 层输入协议
- 设计长期 run state 与 event log
- 设计 LLM 生成 node / arbitration / rule / narration pack 的导入边界
- 设计 LLM 对 `memory`、`rule_engine`、`enforcement` 的结构化提议接口

## 开放设计问题

- 主题分数是否只用于排序，还是要作为启用阈值
- 单节点是否允许主规则 + 附属警示规则
- `sanity` 或 pressure 是否应按 shock 类型分桶
- 旁白模板是否应支持按规则单独配置
