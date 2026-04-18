# Loombound 术语表

代码、注释、README、文档全以此为准。遇到歧义时以本文件为准。

---

## 数据抽象层级（A0–A3）
这一层级由数据本身决定。

An 描述的是数据的**语义解释层级**，而非存储格式。同一份数据可以在不同上下文中有不同层级的解释——例如展开后的散文字符串物理上是 A0 存储，但其语义属于 A1。A0 最精确，A∞ 最抽象；每一层是上层的输入基础，也是下层的压缩产物。

| 层 | 在本系统中的含义 | 示例 |
|---|---|---|
| **A0** | 精确整数、枚举与字符串，可完全还原 | `HP=7`、`depth=3`、`mark: lamp_oil`、散文作为字符串 |
| **A1** | 具体情境骨架：场景遭遇、选项结构——有地点氛围意图，散文蕴含的 A1 语义，无精确数值 | `scene: market offer`、`option: buy the idol` |
| **A2** | 叙事倾向：状态倾向带与分类标签，有限词汇，无法精确还原 | `"sanity: low"`、`"bearing: hollowing"`、`"toll: destabilizing"` |
| **A3** | 创作意图：theme、tone、世界观——C3 据此生成约束结构交给低层 | `"dark souls folk horror"`、tone 描述 |
| **A∞** | 系统设计本身：框架规则、模块边界、不变式——只被 C∞ 修改 | glossary、architecture.md |

系统处理各信息时所在的语义层级：

| 层 | 信息 |
|---|---|
| **A0** | `HP`、`money`、`sanity`、`depth`、`act`、`max_health`；`active_marks`、`major_events`、`traumas`；`sanity_cost`、effects 数值；`waypoint_id`、`option_id`、`context_id`、`decision_type`、`entry_id`（字符串存储）；展开后的散文（字符串存储） |
| **A1** | `scene_concept`、选项骨架（label、意图描述）；A1 cache table 内容；saga waypoint 图（拓扑、`next_waypoints`）；`map_blurb`；`narration_table.json`（per-saga，C3 生成） |
| **A2** | bearing 条目（A2 cache table）；`toll` 标签；toll lexicon 条目；tendency 描述（`"sanity: low"`）；`rules.json` 规则（主题约束） |
| **A3** | saga theme 字符串；tone 描述；世界观/叙事基调 |
| **A∞** | glossary、architecture.md；An/Cn 框架本身 |

**这些名词的语义存在于不同层级的解释，这张表给这些名词一个适当的类型以供系统处理。**

层级越高，数据的变化频率越低、生命周期越长、越难被低层事件撼动：A0 每次 encounter 都在变，A1 per-waypoint 固定，A2 per-saga 固定，A3 由 C∞（人类）写定后极少改变。这是高层能约束低层的基础——低层的频繁变化不会反向修改高层的定义。

---

## 处理核心（C0–C3）
这一层级由核心本身决定。
Cn 核心能高效理解并处理直到 An 层次的信息，但高阶 Cn 核心相当昂贵。

Cn 的命名反映**驱动决策所需的最高抽象层级**。两条核心规律：
- **Cn 可以参考 An 及以下任意层信息；改变 Am 层数据的决策必须来自 C(m+1) 或更高层，执行可以由更低的 Cn 负责。** 例如 C2 读 A0 数值作参考，决策 effects 后交由 C0 写入；A2 层数据由 C3 决策，C2 只读不写。
- **Cn 不需要理解高于 An 的信息。** 高阶核心的决策对低阶核心是黑盒指令——C0 执行 `sanity -= 2` 不需要知道背后的叙事倾向，C1 展开场景骨架不需要知道 bearing 是什么。

在本系统中：C0 = 确定性处理器、C1 = gemma3（本地）、C2 = Haiku、C3 = Opus。

| 名称 | 模型 | 参考层 | 输出层 | 触发时机 |
|---|---|---|---|---|
| **C0** | 本地确定性处理器（无 LLM） | A0 + C2 指令 | A0（执行 effects，更新精确状态） | 运行时 |
| **C1** | gemma3:4b（本地 ollama） | A1 骨架 + C2 指令 | A0（散文字符串） | 运行时 |
| **C2** | claude-haiku-4-5 | A2（倾向框架） | A0（effects 数值）+ A1（tolls、bearing） | 离线（`gen`） + 运行时 |
| **C3** | claude-opus-4-6 | A3（创作意图） | A2（cache table、toll lexicon、rules）+ A1（saga 图、waypoint 结构、narration_table） | 离线（`gen`） |
| **C∞（人类）** | — | A∞（任意层） | A∞（任意层） | 离线，驱动 C3 |

系统设计的目标是**最小化 C∞ 的介入频率**，将工作下放至足够低层的 Cn。C∞ 介入一次（写 A3 意图），C3 负责将其转化为低层约束，之后 C2/C1/C0 自主运行。**因为 Cn 在 n 足够大的时候相当昂贵**。

---

## 缓存层（四个不同的东西）

缓存表命名与其数据的抽象层级对应：A2 cache table 存 A2 层数据，由 C2 使用；A1 cache table 存 A1 层数据，由 C1 使用（C2 使用其子集 A1 option index）。

| 名称 | 存储位置 | 生成时机 | 生命周期 | 用途 |
|---|---|---|---|---|
| **A2 cache table** | `data/a2_cache_table.json` | 一次性（C3） | 全局，跨 saga | bearing 枚举（~50 条），C2 运行时 prompt cache |
| **A1 cache table** | `data/waypoints/<id>/a1_cache_table.json` | 每次 gen（C2） | per-saga | per-waypoint 场景骨架：scene_concept、选项结构、effects |
| **A1 option index** | 不落文件，运行时派生 | 运行时启动 | per-session | A1 cache table 去掉 effects，作为 C2 per-saga cached prefix |
| **PrefetchCache** | 内存，不持久化 | 运行时 | per-session | 预取的 waypoint 内容 + C2 返回的 per-option effects 和 tolls |

> **Anthropic prompt cache** 是 API 层的 token 缓存，与以上四个概念无关，不在本表中。

> **A2 cache table vs A1 cache table**：两者正交，不是子集关系。A2 cache table 是"bearing 词汇表"（全局，C2 用来分类当前叙事走向）；A1 cache table 是"本 saga 的场景骨架"（per-saga，C1 用来展开文字，C2 用 A1 option index 了解当前选项）。

---

## 领域词

| 词 | 定义 |
|---|---|
| **saga** | 一次生成的叙事图：waypoint 拓扑、tone、initial state、toll lexicon |
| **waypoint** | 图中的一个地点，有 node_type、depth、N 个 encounters |
| **encounter** | 一次决策时刻：context + options → 玩家选择 → result（包含 effects） |
| **toll** | 单个选项的后果标签（`stable` / `destabilizing` / 主题词），C2 运行时生成 |
| **toll lexicon** | saga 专属 toll 词汇表，C3 生成，存为 `data/sagas/<id>_toll_lexicon.json`，运行时附在 A1 option index 后缓存 |
| **bearing** | 当前叙事轨迹的分类结果，表示为 A2 cache table 的 `entry_id` |
| **tendency** | C0 精确数值压缩为叙事倾向（low/moderate/high）后发给 C2 的文本描述（A2 层数据） |
| **depth** | waypoint 在 saga 图中的深度层级，严格递增 |
| **mark** | 挂在玩家身上的持久状态标签（如 `lamp_oil`、`warding_tools`） |

---

## 工作流阶段

| 阶段 | 命令 | 核心 | 产出 |
|---|---|---|---|
| **arc palette** | `./loombound arc-palette` | C3（一次性） | `data/a2_cache_table.json` |
| **gen** | `./loombound gen "theme"` | C3 + C2 | `data/sagas/<id>.json` + `data/sagas/<id>_toll_lexicon.json` + `data/sagas/<id>_rules.json` + `data/sagas/<id>_narration_table.json` + `data/waypoints/<id>/a1_cache_table.json` |
| **run** | `./loombound run` | C2 + C1 | 游戏会话，无持久化产出 |
| **report** | `./loombound report` | 无 | 从 `logs/llm.md` 解析 token 用量报表 |

---

## 代码目录结构

详见 [architecture.md](architecture.md)。各层职责摘要：

| 目录 | 层 | 职责 |
|---|---|---|
| `src/t0/memory/` | A0 | CoreState、RunMemory、WaypointMemory 等数据模型 |
| `src/t0/core/` | C0 | enforcement、rule_engine、state_adapter、signal_interpretation |
| `src/t1/memory/` | A1 | scene_concept、选项骨架等数据模型 |
| `src/t1/core/` | C1 | fast_core、narration |
| `src/t2/memory/` | A2 | bearing 条目、toll lexicon 等数据模型 |
| `src/t2/core/` | C2 | classifier、prefetch |
| `src/t3/core/` | C3 | saga 生成逻辑 |
| `src/runtime/` | 组装点 | play_cli、session、saga 加载；可 import 全部层的位置 |
