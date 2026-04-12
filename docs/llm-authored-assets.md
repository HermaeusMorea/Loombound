# LLM 生成内容资产

本文档描述由 LLM 生成的内容应如何进入 `black-archive`。

当前项目方向保持不变：

- 游戏运行在 CLI 中
- 当前可玩的前端是 ANSI HUD 展示层
- 决定论 kernel 负责状态更新与规则执行
- 手写 JSON 与 LLM 生成资产共同构成内容来源
- LLM 是必需内容层，并且必须通过同样的结构化边界进入系统

## 核心原则

当前架构非常适合做成“结构化内容生成 + 受约束的 LLM 参与层”，而不是让 LLM 直接接管游戏。

职责划分应保持如下：

- kernel 拥有：
  - 状态结构
  - 合法更新
  - 最终规则选择与最终应用
  - replay/debug 的一致性
- LLM 负责：
  - 结构化 JSON 内容生成
  - 生成与预载 node、arbitration、rule、narration 等资产
  - memory 总结与 meta 描述
  - rule bias、enforcement flavor、narration 的提议

所有 LLM 输出都应经过：

- `state_adapter`
- schema 校验
- allowlist / registry 校验

一句话：

- **LLM 可以提议**
- **kernel 负责验收和落地**

## 目标

LLM 生成内容是当前项目的必需能力，最适合承担这些事情：

- 生成与预载节点
- 生成 arbitration 场景细节
- 生成更丰富的 narration
- 形成长期的 meta 描述
- 提议 rule bias 与 enforcement flavor

LLM 不应该取代 kernel 对这些事情的责任：

- 校验结构
- 选择合法状态更新
- 应用规则惩罚
- 保持 `Run`、`Node`、`Arbitration` 的一致性

## 建议的接口类别

### 1. 内容生成接口

让 LLM 生成结构化内容包，例如：

- `campaign pack`
- `node pack`
- `arbitration pack`
- `rule pack`
- `narration pack`

例如：

- `generate_node_pack(run_state, run_memory, theme)`
- `generate_arbitration_pack(node_context, meta_summary)`

输出必须是 JSON 或其他严格结构化表示，而不是自由散文。

### 2. `rule_engine` 预载接口

LLM 不应直接选择最终规则。

更合适的是让它：

- 预生成候选规则
- 提议 theme bias
- 提议 scene tags
- 提议某个 node 更适合强调哪类 pressure

例如：

- `propose_rule_bias(arbitration_context, run_memory)`
- `generate_rule_pack(campaign_tone)`

之后由 kernel 决定：

- 是否接受这份提议
- 如何合并进 `RuleSystem`

### 3. `memory` 接口

这是最适合接入 LLM 的位置之一。

LLM 可以做：

- `NodeMemory -> textual summary`
- `RunMemory -> meta description`
- 从长期事件中提炼：
  - trauma
  - obsession
  - fear pattern
  - recurring symbols

例如：

- `summarize_node_memory(node_memory, run_memory)`
- `derive_meta_state(run_memory)`

这些输出最适合写入：

- `MetaState.metadata`
- narrator tone hints
- 长期角色漂移总结

### 4. `narration` 接口

这是当前最安全、也最容易见效果的接入点。

LLM 可以根据已确定结果生成：

- opening
- judgement
- warning
- aftermath text

输入应保持结构化、以决定论结果为主，例如：

- arbitration
- selected rule
- option result
- node summary
- run memory summary

输出仍应是结构化 narration JSON。

### 5. `enforcement` 预载接口

这一块需要最强约束。

LLM **不应该**直接写 `CoreState`。

它可以：

- 生成候选 effect packs
- 提议 trauma/event 文本
- 提议基于 allowlisted effect template 的组合

例如：

- `propose_effect_flavor(...)`
- `propose_meta_consequences(...)`

最终写回仍然必须限制在白名单字段：

- `health_delta`
- `money_delta`
- `sanity_delta`
- `add_conditions`
- `add_events`
- `add_traumas`

## 建议的资产类型

### Campaign Pack

结构化 campaign 内容，例如：

- 地图布局
- node 顺序
- 初始状态
- 高层语气

### Node Pack

结构化 node 内容，例如：

- node label
- map blurb
- linked arbitrations
- 预载 flavor

### Arbitration Pack

结构化 scene 内容，例如：

- scene summary
- 玩家可见问题
- options
- tags
- authored effects

### Rule Pack

结构化规则，最终仍映射到 `RuleTemplate`。

适合用于：

- 临时规则集
- 特定语气下的规则变体
- 某个 campaign 的压力模式

### Narration Pack

结构化 narration 模板，例如：

- opening
- judgement
- warning

它应该用于丰富呈现，而不是覆盖决定论结果。

## 必须保持的边界

所有 LLM 生成资产都应满足这些规则。

### 结构优先

- 内容必须映射到已知 schema 或内部 dataclass 形状
- 不能只给自由文本

### 先走适配层

- LLM 输出应先进入 `state_adapter`
- `state_adapter` 负责正规化字段、拒绝未知结构、在合适时填入安全默认值

### 状态更新由 kernel 负责

- LLM 可以提议内容
- LLM 可以丰富描述
- LLM 可以生成和预载节点
- LLM 不应直接修改 `Run`、`Node`、`CoreStateView` 或 `MetaStateView`

### 可回放

- 生成内容应能保存为 JSON
- 同一份生成资产应可重复用于 replay 与调试

## 建议流程

1. LLM 生成结构化资产
2. `state_adapter` 加载并正规化它
3. kernel 校验其形状与边界
4. runtime 在正常的 `Run -> Node -> Arbitration` 流程中使用它
5. narration 可以在决定论结果确定之后再增加 flavor

简写形式：

`LLM JSON -> state_adapter -> validate -> normalize -> runtime`

## 预载生成节奏

对当前项目来说，最合适的不是“走到哪里再临时生成到哪里”，而是：

- 前台游玩
- 后台预载

更具体地说：

### 1. `Run` 绑定全局背景设定

一局开始时，应先固定一份 run 级背景包，例如：

- 世界设定
- 当前 campaign tone
- 关键 faction / symbols / threats
- 可能的剧本母题

这相当于整局的内容母板。

### 2. 当前 `Node` 游玩时，后台生成后续 2 到 3 个 `Node`

生成输入可以包括：

- `Run.core_state`
- `Run.meta_state`
- `Run.memory`
- 当前 node summary
- run 绑定的背景设定

生成输出则应是结构化包，例如：

- 候选后续 `node packs`
- 每个 node 内的 `arbitration packs`
- 可选 `narration packs`
- 可选 `meta summaries`

### 3. 进入下一个 node 时优先消费已预载内容

如果后台已经生成完成，就直接从缓存中取用。

如果尚未完成，则使用：

- 手写 authored 内容
- 或更轻量的即时生成 fallback

### 4. 始终维持一个短前瞻窗口

推荐策略不是一次性生成整局，而是：

- 始终保持前方 2 到 3 个 `Node` 的缓存
- 每个 node 内保持 1 到 3 个 `Arbitration` 已经准备好

这样可以兼顾：

- 世界连续性
- memory 驱动生成
- 生成速度
- 内容不过早失真

### 5. 预载内容允许失效并重生成

当某次 arbitration 之后，`RunMemory`、`MetaState` 或核心状态变化过大时：

- 先检查已预载内容是否仍然适配
- 将不再适配的内容标记为 `stale`
- 再后台重新生成替代内容

因此，预载包最好带有：

- `status = pending / ready / failed / stale`
- `source = authored / llm_generated / hybrid`

## 远程强模型与本地模型的协作

对于这个项目，最适合的不是只用一种模型，而是：

- 远程强力 LLM 作为主生成器
- 本地 LLM 作为补位、降级和快速小任务模型

### 为什么远程强模型更适合作为主生成器

因为项目要生成的是：

- `node pack`
- `arbitration pack`
- `rule pack`
- `memory summary`
- `narration pack`

这类任务通常需要：

- 更长上下文
- 更稳定的结构化输出
- 更高的一致性
- 更强的世界细节质量

因此，主生成层更适合交给远程强模型。

### 本地模型更适合做什么

本地模型更适合承担：

- narration 改写
- memory 小总结
- 已有 pack 的轻量变体
- 局部补全
- 无网 fallback
- 非关键内容的快速草拟

### 推荐的 provider 策略

推荐在 `llm_interface` 中支持多 provider，但默认策略是：

- `remote_primary`
- `local_fallback`

也就是说：

- 主生成任务交给远程强模型
- 本地模型负责补位、离线兜底和轻量变体

这种组合最符合当前项目的设计目标：

- 内容质量要足够高
- 生成速度要可接受
- 运行时要有 fallback
- 架构上不把整个项目绑死到单一 provider

## 省 token 的协作策略

为了控制成本，不推荐让远程强模型直接返回完整的 node / arbitration 全文内容。

更适合当前项目的方式是：

- 远程强模型返回高价值、压缩后的结构化骨架
- 本地模型根据这些骨架做低成本展开与演出

一句话：

- **远程模型负责高价值压缩决策**
- **本地模型负责低成本展开与表演**

### 远程模型适合返回什么

远程模型最适合输出：

- 关键词
- scene beats
- 主题标签
- 核心冲突
- option intent labels
- rule bias 提示
- narration directives
- 少量关键句

例如一个远程返回的 seed 可以像这样：

- `node_theme`
- `scene_core`
- `arbitration_axes`
- `narration_style`

这些内容 token 成本低，但信息密度高。

### 本地模型适合补全什么

本地模型更适合根据这些 seed 展开成：

- scene summary
- question text
- option wording
- narration text
- aftermath text

也就是说：

- 远程模型负责决定“这一段内容的本质是什么”
- 本地模型负责把它写成玩家看到的具体文本

## 两层资产模型

为了让这种协作清晰可维护，推荐把资产分成两层：

### 1. `seed pack`

由远程强模型生成。

它保存：

- 高压缩结构
- 关键词
- 风格标签
- 核心冲突
- 意象与方向

它不直接用于 runtime 最终消费，而更像：

- 内容生成草图
- 高价值提示包

### 2. `resolved pack`

由本地模型或后续处理流程展开生成。

它保存：

- 最终 node 文本
- 最终 arbitration 文本
- 最终 narration 文本
- 最终结构化 fields

它才是进入 `state_adapter` 和 runtime 的直接候选内容。

推荐流程：

`remote seed -> local expansion -> state_adapter -> validate -> runtime`

## 慢节奏显示作为生成缓冲

CLI 的慢节奏显示不仅是风格选择，也可以成为生成缓冲机制。

具体来说：

- HUD 先显示
- scene opening 可以先显示
- question 再显示
- options 最后显示

这样可以：

- 给本地模型留下补全文本的时间
- 减少玩家等待“整段一次生成完”的卡顿
- 让游戏节奏更有仪式感

因此，展示层可以有意识地支持：

- 分段显示
- 逐段展开
- 在不影响体验的情况下，为本地生成争取时间

## 建议新增的模块边界

如果项目要新增专门的 LLM 集成层，最合适的模块名是：

- `llm_interface`

备选名：

- `llm_bridge`

推荐职责：

- prompt 输入装配
- 模型调用
- 结构化响应解析
- 将结果交给 `state_adapter`

这样边界会很清楚：

- `authoring`
  - 手写内容
- `llm_interface`
  - 动态生成内容
- `state_adapter`
  - 正规化与校验边界
- `runtime` / kernel 各模块
  - 真正消费并应用内容

## 建议的接入顺序

按照安全性和收益排序，最合适的顺序是：

1. `narration`
2. `memory summary`
3. `node/arbitration pack generation`
4. `rule pack generation`
5. `enforcement proposal`

原因是：

- narration 最安全，也最容易立刻看到效果
- memory summary 很适合这个项目
- 内容包生成能显著提高生产效率
- rule 生成需要更严格的 schema
- enforcement proposal 约束要求最高

## 输出家族

作为一个实用规则，LLM 接口最好只返回两大类输出。

### A. 内容包

- `node`
- `arbitration`
- `rule`
- `narration`

### B. 提议包

- `meta_summary`
- `rule_bias`
- `effect_suggestion`

## 合适的用法

- 基于 `RunMemory` 预载接下来两个 node
- 直接生成 campaign、node、arbitration 的结构化草案
- 为闹鬼街区生成多份 arbitration 场景草案
- 生成不同语气的 narration pack
- 生成近期预兆、恐惧、重复意象等 meta 描述

## 不合适的用法

- 让 LLM 直接重写 core stats
- 让 LLM 在运行时发明未支持的 effect 字段
- 绕过 `RuleTemplate`，直接注入自由文本规则
- 用原始 LLM judgement 直接替代决定论 verdict

## 与当前仓库的关系

在当前项目里：

- `authoring` 持有 authored JSON 资产
- `state_adapter` 是加载与正规化边界
- `runtime` 消费已校验内容
- `presentation` 负责当前 CLI HUD
- `rule_engine`、`enforcement`、`memory` 仍保持决定论

所以 LLM 的长期角色应该是：

- 内容资产生成
- 世界细节生成
- 文本增强
- 节点与 arbitration 的预载
- rule / enforcement / memory 的结构化提议

而不是直接替代 kernel。
