# 仓库总结

这份文档用于快速向外部大模型或协作者说明 `loombound` 当前的项目结构、工作流和后续方向。

## 项目是什么

`loombound` 是一个运行在 CLI 中的文字冒险 / 跑团风格原型游戏。

当前主题偏：

- 克苏鲁式心智压力
- 叙事裁决
- 地图推进
- 节点内多次选择事件

项目目前的核心目标不是接外部游戏，也不是图形界面，而是先把一套可玩的运行时结构做稳：

- `Run -> Node -> Arbitration`
- 决定论规则内核
- `RunMemory / NodeMemory`
- CLI HUD 展示
- LLM 参与内容生成、预载和结构化提议

## 当前高层设计

### 运行时对象

- `Run`
  - 一整局游戏
  - 持有全局 `CoreState`、`MetaState`、`RunMemory`、`RuleSystem`

- `Node`
  - 地图上的一个节点 / 场景
  - 持有 `NodeMemory`、`NodeRuleState`
  - 一个 node 内可以有多个 `Arbitration`

- `Arbitration`
  - 单次事件选择 / 裁决单元
  - 包含 `Arbitration.context`、options、result

### 状态层

- `CoreState`
  - 结构化、决定论、立即生效的状态
  - 当前主要包括：
    - `health`
    - `money`
    - `sanity`
    - `floor`
    - `act`

- `MetaState`
  - 解释层 / 叙事层状态
  - 当前主要包括：
    - `active_conditions`
    - `metadata`
      - `major_events`
      - `traumas`
      - 未来的 meta summaries

### 记忆层

- `RunMemory`
  - 跨节点长期存在
  - 保存：
    - `sanity`
    - `recent_rules`
    - `recent_shocks`
    - `theme_counters`
    - `behavior_counters`
    - `important_incidents`
    - `narrator_mood`

- `NodeMemory`
  - 节点内短期存在
  - 保存：
    - `events`
    - `choices_made`
    - `shocks_in_node`
    - `sanity_lost_in_node`
    - `important_flags`
    - `node_summary`

## 当前目录结构

### 核心代码目录

`src/core/`

当前按 11 个模块组织：

1. `deterministic_kernel`
2. `state_adapter`
3. `signal_interpretation`
4. `rule_engine`
5. `enforcement`
6. `llm_interface`
7. `presentation`
8. `narration`
9. `memory`
10. `authoring`
11. `runtime`

### 各模块职责

#### `runtime`

负责游戏运行时主流程与生命周期：

- `Run`
- `Node`
- `Arbitration`
- campaign 初始化
- CLI gameplay loop

关键文件：

- `src/core/runtime/session.py`
- `src/core/runtime/campaign.py`
- `src/core/runtime/play_cli.py`

#### `deterministic_kernel`

负责共享核心数据模型：

- `CoreStateView`
- `MetaStateView`
- `ArbitrationContext`
- `RuleTemplate`
- `RuleEvaluation`
- `OptionResult`
- `ArbitrationResult`
- `NodeSummary`
- `RunSnapshot`

关键文件：

- `src/core/deterministic_kernel/models.py`

#### `state_adapter`

负责把外部内容装配成内部对象：

- authored JSON -> internal runtime objects
- 未来 LLM packs -> internal runtime objects

关键文件：

- `src/core/state_adapter/context_builder.py`

#### `signal_interpretation`

负责从 scene/context 中提取信号和主题分数：

- `build_signals(...)`
- `score_themes(...)`

关键文件：

- `src/core/signal_interpretation/signals.py`
- `src/core/signal_interpretation/theme_scorer.py`

#### `rule_engine`

负责规则系统状态和规则选择：

- `RuleSystem`
- `NodeRuleState`
- `evaluate_rules(...)`
- `select_rule(...)`
- `build_selection_trace(...)`

关键文件：

- `src/core/rule_engine/rule_matcher.py`
- `src/core/rule_engine/rule_selector.py`
- `src/core/rule_engine/state.py`

#### `enforcement`

负责把规则落到选项上，并把选项效果写回状态：

- `enforce_rule(...)`
- `apply_option_effects(...)`

关键文件：

- `src/core/enforcement/enforcement.py`
- `src/core/enforcement/effects.py`

#### `llm_interface`

负责 LLM 协作层骨架：

- `SeedPack`
- `ResolvedPack`
- `GenerationJob`
- 远程主生成 provider 占位
- 本地 fallback provider 占位

当前还只是 skeleton，还没真正接 provider。

关键文件：

- `src/core/llm_interface/types.py`
- `src/core/llm_interface/providers.py`

#### `presentation`

负责 CLI 展示层：

- 顶部 HUD
- 状态面板
- arbitration 场景区
- result 区
- map 区
- 输入提示区

当前使用 ANSI 颜色和 box 布局，窄终端会自动从双栏回退为上下堆叠。

关键文件：

- `src/core/presentation/cli.py`

#### `narration`

负责文字演出生成。

当前仍是决定论模板渲染，未来会接 LLM narration。

关键文件：

- `src/core/narration/narrator.py`

#### `memory`

负责 memory 类型和记录逻辑：

- `RunMemory`
- `NodeMemory`
- `NodeEvent`
- `NodeChoiceRecord`
- `ShockRecord`
- `update_after_node(...)`
- node 记录辅助函数

关键文件：

- `src/core/memory/types.py`
- `src/core/memory/run_memory.py`
- `src/core/memory/recording.py`

#### `authoring`

负责内容资产加载：

- 规则
- narration templates
- 未来 campaign/node/arbitration 资产管理

关键文件：

- `src/core/authoring/assets.py`

## 数据目录结构

`data/`

- `data/campaigns/act1_campaign.json`
  - 当前唯一 campaign

- `data/nodes/`
  - 节点内容
  - 当前有：
    - `crossroads_01.json`
    - `night_market_01.json`
    - `archive_stack_01.json`
    - `river_crossing_01.json`

- `data/arbitrations/`
  - 单次事件选择内容
  - 当前有：
    - `crossroads_01.json`
    - `market_01.json`
    - `artifact_offer_01.json`
    - `omens_01.json`
    - `whisper_offer_01.json`

- `data/rules/rules.small.json`
  - 当前规则集

- `data/text/narration_templates.json`
  - narration 模板

## Schema 与文档

- `schemas/arbitration.schema.json`
- `schemas/arbitration-result.schema.json`
- `schemas/rule.schema.json`

- `docs/system-architecture.md`
- `docs/llm-authored-assets.md`
- `tasks/backlog.md`

## 当前游戏工作流

### 玩家可见工作流

1. 启动 `play_cli`
2. 读取 campaign
3. 初始化 `Run`
4. 进入起始 `Node`
5. 节点内顺序处理一个或多个 `Arbitration`
6. 每次 arbitration：
   - 显示当前状态
   - 显示场景描述
   - 显示选项
   - 玩家输入选择
   - 规则系统裁决
   - 状态更新
   - 显示结果
7. 节点结束后：
   - 汇总到 `RunMemory`
8. 回到地图继续选下一个 node
9. 没有后续节点后结束 run

### 代码中的主调用链

主入口：

- `python -m src.core.runtime.play_cli`

核心流程大致是：

1. `runtime.play_cli` 读取 campaign
2. `authoring` 加载 rules / templates
3. `runtime.make_run(...)` 创建 `Run`
4. `runtime._play_node(...)` 进入 node
5. `state_adapter` 加载 arbitration JSON
6. `signal_interpretation` 提取 signals / themes
7. `rule_engine` 匹配并选择规则
8. `enforcement` 生成 option verdict，并应用选项效果
9. `memory` 记录 node 事件和 choice
10. `narration` 生成演出文本
11. `presentation` 渲染 HUD
12. 节点结束后 `update_after_node(...)`

## 当前规则与裁决风格

当前裁决输出主要是：

- `stable`
- `destabilizing`

并伴随：

- `sanity_cost`
- `sanity_delta`

当前主题包括：

- `clarity`
- `composure`
- `self_preservation`
- `detachment`

## 当前 UI 状态

当前 CLI 已经不是日志式 demo，而是一个可玩的终端界面：

- 顶部 HUD
- 中间内容区
- 底部输入区

特点：

- ANSI 颜色
- box 布局
- 双栏与窄终端堆叠 fallback
- 输入前有固定 Input box

仍然不是：

- 真正的 TUI widget 系统
- `textual` / `curses` 风格的局部刷新 HUD

## 当前 LLM 设计方向

项目已经决定：

- LLM 是必需层
- 但不直接替代 kernel

### LLM 负责

- 自动生成内容资产
- 预载后续 node / arbitration
- 生成 narration
- 总结 memory
- 整理 `MetaState`
- 提议 rule bias / enforcement flavor / meta consequences

### kernel 负责

- 状态结构
- 合法更新
- 最终规则选择
- 最终执行与落地
- replay/debug 一致性

## 当前已经确定的 LLM 协作模式

### 1. 前台游玩，后台预载

推荐模式不是“走到哪现生成到哪”，而是：

- 当前 `Node` 前台游玩
- 后台根据：
  - `Run.core_state`
  - `Run.meta_state`
  - `Run.memory`
  - run 背景设定
  - 当前 node summary
  预载后面 2 到 3 个 `Node` 及其 `Arbitration`

### 2. 远程强模型 + 本地模型协作

已经决定的方向是：

- 远程强模型作为主生成器
- 本地 Gemma 9B 之类模型作为补位 / fallback / expansion 模型

### 3. 两层资产模型

#### `seed pack`

由远程强模型生成，负责：

- 高信息密度骨架
- 关键词
- 冲突轴
- 风格标签
- 关键意象
- 规则偏置建议

#### `resolved pack`

由本地模型或后续流程展开，负责：

- 最终场景文本
- 最终 arbitration 文本
- 最终 narration 文本
- 结构化字段补全

推荐流程：

`remote seed -> local expansion -> state_adapter -> validate -> runtime`

### 4. 慢节奏显示作为生成缓冲

项目还希望利用 CLI 的节奏感：

- HUD 先显示
- scene opening 后显示
- question 再显示
- options 最后显示

这样既有气氛，也给本地模型补全文本留出时间。

## 当前已经做完到什么程度

已经完成：

- 可玩的 CLI loop
- `Run / Node / Arbitration`
- `RunMemory / NodeMemory`
- 基础规则系统
- 基础 enforcement
- ANSI HUD
- 窄终端 fallback
- `llm_interface` 骨架
- LLM-first 的文档方向

还没完成：

- 真正的 `llm_interface` provider 实现
- seed pack / resolved pack 的正式 schema
- LLM 后台预载 job 调度
- 更丰富的 campaign 内容
- 更完整的中文化体验
- `textual` 版真固定 HUD

## 当前最值得讨论的未来方向

如果把这份文档丢给外部大模型，最值得继续讨论的问题大概是：

1. `seed pack` 和 `resolved pack` 的正式 JSON 结构应该怎么设计？
2. `llm_interface` 应该如何组织：
   - `remote_primary`
   - `local_fallback`
   - background generation jobs
3. 后台预载和 stale content 该如何管理？
4. rule pack 中哪些部分可以让 LLM 生成，哪些必须强约束？
5. 中文化后，CLI 展示层是否要切到 `textual`？
6. 如何以最低 token 成本实现高质量内容生成？

## 一句话总结

这个仓库现在已经不是概念 demo，而是：

**一个可玩的 CLI 叙事游戏原型，拥有清晰的运行时模型、规则系统、记忆结构和初步的 LLM 内容管线方向。**
