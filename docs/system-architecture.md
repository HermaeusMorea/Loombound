# System Architecture

## Design Goal

构建一个离线、可检查、可调试的外部规则引擎。LLM 或更复杂的生成层以后再接入，但不应成为第一层判断来源。

## Pipeline

1. `choice context`
2. `signals`
3. `theme scoring`
4. `rule matching`
5. `rule selection`
6. `enforcement`
7. `optional narration`
8. `run snapshot`

## Module Responsibilities

### `models.py`

定义 context、rule、evaluation、snapshot 等核心数据结构。

### `signals.py`

从输入上下文抽取决定论信号，例如：

- 决策类型
- 当前阶段
- 资源压力
- 选项标签
- 是否存在“安全 / 节制 / 高风险 / 贪取”线索

### `theme_scorer.py`

将局势映射到礼制主题分数，例如：

- `order`
- `restraint`
- `avoid_conflict`
- `humility`

### `rule_matcher.py`

判断某条规则是否适用于当前 context，并记录命中原因。

### `rule_selector.py`

在适用规则中做稳定选择。第一版采用：

- 主题吻合度
- 规则优先级
- `id` 字典序

### `enforcement.py`

依据规则对选项做标记，并给出：

- 守礼/违礼状态
- 原因
- `ritual_collapse_delta`

### `narrator.py`

从模板库中生成可选旁白。旁白是附加层，可关闭，不应依赖外部模型。

## Data Boundaries

- `data/rules/` 保存规则模板
- `data/text/` 保存旁白模板
- `data/sample_contexts/` 保存样例输入
- `schemas/` 约束 JSON 结构

## Important Architectural Decisions

- 规则与文案分离
- 输入上下文与游戏 API 分离
- 规则执行与最终游戏惩罚分离
- 先做单条规则生效，再讨论多规则叠加

## Deferred Questions

- 一个 context 是否允许多条规则并行生效
- `ritual_collapse` 如何映射为长期后果
- 如何处理例外条款与冲突规则
- 将来与真实游戏状态对接时，哪些字段属于 adapter 层

