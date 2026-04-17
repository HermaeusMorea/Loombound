# Loombound 术语表

代码、注释、README、文档全以此为准。遇到歧义时以本文件为准。

---

## AI 角色

| 名称 | 模型 | 触发时机 | 职责 |
|---|---|---|---|
| **Opus** | claude-opus-4-6 | 离线（`gen`） | 生成 campaign 图 + verdict dict；一次性生成 T2 cache table |
| **Haiku** | claude-haiku-4-5 | 离线（`gen`） + 运行时 | 离线：生成 T1 cache table；运行时：M2 分类器 |
| **Fast Core** | gemma3:4b（本地 ollama） | 运行时 | 场景文本展开（T1 cache skeleton → 完整 arbitration 文字） |

---

## 缓存层（四个不同的东西）

| 名称 | 存储位置 | 生成时机 | 生命周期 | 用途 |
|---|---|---|---|---|
| **T2 cache table** | `data/t2_cache_table.json` | 一次性（Opus） | 全局，跨 campaign | arc-state 枚举（~50 条），Haiku 运行时 prompt cache |
| **T1 cache table** | `data/nodes/<id>/t1_cache_table.json` | 每次 gen（Haiku） | per-campaign | per-node 场景骨架：scene_concept、选项结构、effects |
| **T1 option index** | 不落文件，运行时派生 | 运行时启动 | per-session | T1 cache 去掉 effects，作为 Haiku per-campaign cached prefix |
| **PrefetchCache** | 内存，不持久化 | 运行时 | per-session | 预取的节点内容 + M2 返回的 per-option effects 和 verdicts |

> **Anthropic prompt cache** 是 API 层的 token 缓存，与以上四个概念无关，不在本表中。

---

## 记忆层（M0 / M1 / M2）

| 层 | 对应实体 | 语言类型 | 职责 |
|---|---|---|---|
| **M0 / Kernel** | `RunMemory`、`NodeMemory` | 精确整数 + 枚举 | 确定性状态：HP、金钱、理智、事件历史 |
| **M1 / Fast Core** | gemma3（本地） | quasi ↔ 自然语言 | 将 T1 cache skeleton + arc tendency → 展开为完整场景文字 |
| **M2 / Haiku** | `M2Classifier` | quasi 语言 | 分类当前 arc state（entry_id）+ 为下一个 arb 输出 per-option effects 和 verdicts |

---

## 领域词

| 词 | 定义 |
|---|---|
| **campaign** | 一次生成的叙事图：节点拓扑、tone、initial state、verdict_dict |
| **node** | 图中的一个地点，有 node_type、floor、N 个 arbitrations |
| **arbitration** | 一次决策时刻：context + options → 玩家选择 → result（包含 effects） |
| **verdict** | 单个选项的后果标签（`stable` / `destabilizing` / 主题词），M2 运行时生成 |
| **verdict_dict** | campaign 专属 verdict 词汇表，Opus 生成，存在 campaign.json，运行时附在 T1 option index 后缓存 |
| **arc state** | 当前叙事轨迹的分类结果，表示为 T2 cache table 的 `entry_id` |
| **quasi state** | M0 精确数值压缩为倾向带语言（low/moderate/high）后发给 M2 的文本描述 |
| **floor** | 节点在 campaign 图中的深度层级，严格递增 |
| **condition** | 挂在玩家身上的持久状态标签（如 `lamp_oil`、`warding_tools`） |

---

## 工作流阶段

| 阶段 | 命令 | AI | 产出 |
|---|---|---|---|
| **arc palette** | `./loombound arc-palette` | Opus（一次性） | `data/t2_cache_table.json` |
| **gen** | `./loombound gen "theme"` | Opus + Haiku | `data/campaigns/<id>.json` + `data/nodes/<id>/t1_cache_table.json` |
| **run** | `./loombound run` | Haiku（M2）+ gemma3 | 游戏会话，无持久化产出 |
| **report** | `./loombound report` | 无 | 从 `logs/llm.md` 解析 token 用量报表 |

---

## 代码模块边界

| 模块 | 职责 | 不负责什么 |
|---|---|---|
| `deterministic_kernel` | 数据模型（CoreState、Arbitration、RuleTemplate、OptionResult） | 任何 LLM 调用 |
| `memory` | RunMemory、NodeMemory、M1Store、M2Store | 状态更新逻辑 |
| `rule_engine` | 规则匹配与选择（T0，辅助层） | verdict 最终决策（由 M2 负责） |
| `enforcement` | 将 M2 verdict 转为 OptionResult + sanity penalty | 规则内容本身 |
| `signal_interpretation` | 从 arbitration 构建信号和 theme score | 与 LLM 通信 |
| `state_adapter` | 将运行时状态规范化为 LLM 输入格式 | 任何 LLM 调用 |
| `narration` | 从模板渲染叙述文字 | 动态生成文字（由 Fast Core 负责） |
| `authoring` | 加载离线资产（rules.json、narration_templates.json） | 运行时逻辑 |
| `llm_interface` | M2Classifier、FastCore、PrefetchCache、collector | 游戏状态管理 |
| `presentation` | CLI 渲染（不含业务逻辑） | 状态计算 |
| `runtime` | 游戏主循环、session、campaign 加载 | 规则定义、LLM prompt 设计 |
