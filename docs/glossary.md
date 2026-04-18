# Loombound 术语表

代码、注释、README、文档全以此为准。遇到歧义时以本文件为准。

---

## 数据抽象层级（T0–T3）

在本系统中：T0 = 确定性处理器、T1 = gemma3（本地）、T2 = Haiku、T3 = Opus。

Tn 描述的是数据的**语义解释层级**，而非存储格式。同一份数据可以在不同上下文中有不同层级的解释——例如展开后的散文字符串物理上是 T0 存储，但其语义属于 T1。T0 最精确，T3 最抽象；每一层是上层的输入基础，也是下层的压缩产物。

| 层 | 在本系统中的含义 | 示例 |
|---|---|---|
| **T0** | 精确整数、枚举与字符串，可完全还原 | `HP=7`、`floor=3`、`condition: lamp_oil`、展开后的散文作为字符串 |
| **T1** | 具体情境骨架：场景遭遇、选项结构——有地点氛围意图，散文蕴含的T1语义，无精确数值 | `scene: market offer`、`option: buy the idol` |
| **T2** | 叙事倾向：状态倾向带与分类标签，有限词汇，无法精确还原 | `"sanity: low"`、`"arc: hollowing"`、`"verdict: destabilizing"` |
| **T3** | 创作意图：theme、tone、世界观——T3 Core 据此生成约束结构交给低层 | `"dark souls folk horror"`、tone 描述 |

---

## 处理核心（T0–T3 Core）

Tn Core 的命名反映**驱动决策所需的最高抽象层级**，而非输出数据的层级。例如 T2 Core 输出的 effects 包含 T0 精确数值，但因为正确填写这些数值需要理解叙事倾向（T2），所以由 T2 Core 负责。

| 名称 | 模型 | 触发时机 | 职责 |
|---|---|---|---|
| **T0 Core** | 本地确定性处理器（无 LLM） | 运行时 | 确定性状态管理：HP、金钱、理智、事件历史；规则匹配 |
| **T1 Core** | gemma3:4b（本地 ollama） | 运行时 | 将 T1 cache skeleton + arc tendency → 展开为完整场景文字 |
| **T2 Core** | claude-haiku-4-5 | 离线（`gen`） + 运行时 | 离线：生成 T1 cache table；运行时：分类 arc state + 输出 per-option effects 和 verdicts |
| **T3 Core** | claude-opus-4-6 | 离线（`gen`） | 生成 campaign 图 + verdict dict；一次性生成 T2 cache table |

---

## 缓存层（四个不同的东西）

缓存表命名与处理它的核心层级对应：T2 cache table 由 T2 Core 使用，T1 cache table 由 T1 Core 使用（T2 Core 使用其子集 T1 option index）。

| 名称 | 存储位置 | 生成时机 | 生命周期 | 用途 |
|---|---|---|---|---|
| **T2 cache table** | `data/t2_cache_table.json` | 一次性（T3 Core） | 全局，跨 campaign | arc-state 枚举（~50 条），T2 Core 运行时 prompt cache |
| **T1 cache table** | `data/nodes/<id>/t1_cache_table.json` | 每次 gen（T2 Core） | per-campaign | per-node 场景骨架：scene_concept、选项结构、effects |
| **T1 option index** | 不落文件，运行时派生 | 运行时启动 | per-session | T1 cache table 去掉 effects，作为 T2 Core per-campaign cached prefix |
| **PrefetchCache** | 内存，不持久化 | 运行时 | per-session | 预取的节点内容 + T2 Core 返回的 per-option effects 和 verdicts |

> **Anthropic prompt cache** 是 API 层的 token 缓存，与以上四个概念无关，不在本表中。

> **T2 cache table vs T1 cache table**：两者正交，不是子集关系。T2 cache table 是"弧线状态词汇表"（全局，T2 Core 用来分类当前叙事走向）；T1 cache table 是"本 campaign 的场景骨架"（per-campaign，T1 Core 用来展开文字，T2 Core 用 T1 option index 了解当前选项）。

---

## 领域词

| 词 | 定义 |
|---|---|
| **campaign** | 一次生成的叙事图：节点拓扑、tone、initial state、verdict_dict |
| **node** | 图中的一个地点，有 node_type、floor、N 个 arbitrations |
| **arbitration** | 一次决策时刻：context + options → 玩家选择 → result（包含 effects） |
| **verdict** | 单个选项的后果标签（`stable` / `destabilizing` / 主题词），T2 Core 运行时生成 |
| **verdict_dict** | campaign 专属 verdict 词汇表，T3 Core 生成，存在 campaign.json，运行时附在 T1 option index 后缓存 |
| **arc state** | 当前叙事轨迹的分类结果，表示为 T2 cache table 的 `entry_id` |
| **quasi state** | T0 Core 精确数值压缩为倾向带语言（low/moderate/high）后发给 T2 Core 的文本描述 |
| **floor** | 节点在 campaign 图中的深度层级，严格递增 |
| **condition** | 挂在玩家身上的持久状态标签（如 `lamp_oil`、`warding_tools`） |

---

## 工作流阶段

| 阶段 | 命令 | 核心 | 产出 |
|---|---|---|---|
| **arc palette** | `./loombound arc-palette` | T3 Core（一次性） | `data/t2_cache_table.json` |
| **gen** | `./loombound gen "theme"` | T3 Core + T2 Core | `data/campaigns/<id>.json` + `data/nodes/<id>/t1_cache_table.json` |
| **run** | `./loombound run` | T2 Core + T1 Core | 游戏会话，无持久化产出 |
| **report** | `./loombound report` | 无 | 从 `logs/llm.md` 解析 token 用量报表 |

---

## 代码模块边界

| 模块 | 职责 | 不负责什么 |
|---|---|---|
| `deterministic_kernel` | 数据模型（CoreState、Arbitration、RuleTemplate、OptionResult） | 任何 LLM 调用 |
| `memory` | RunMemory、NodeMemory、M1Store、M2Store | 状态更新逻辑 |
| `rule_engine` | 规则匹配与选择（T0 Core，辅助层） | verdict 最终决策（由 T2 Core 负责） |
| `enforcement` | 将 T2 Core verdict 转为 OptionResult + sanity penalty | 规则内容本身 |
| `signal_interpretation` | 从 arbitration 构建信号和 theme score | 与 LLM 通信 |
| `state_adapter` | 将运行时状态规范化为 LLM 输入格式 | 任何 LLM 调用 |
| `narration` | 从模板渲染叙述文字 | 动态生成文字（由 T1 Core 负责） |
| `authoring` | 加载离线资产（rules.json、narration_templates.json） | 运行时逻辑 |
| `llm_interface` | T2 Core classifier、T1 Core、PrefetchCache、collector | 游戏状态管理 |
| `presentation` | CLI 渲染（不含业务逻辑） | 状态计算 |
| `runtime` | 游戏主循环、session、campaign 加载 | 规则定义、LLM prompt 设计 |
