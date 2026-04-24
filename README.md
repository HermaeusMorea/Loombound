# Loombound

> 项目状态
> 本仓库保存的是 Loombound 的上一代可运行原型（V1）。
> 它仍然可以运行，也仍然体现了项目的核心设计思路；
> 但当前正在规划中的新架构将转向 Opus -> Haiku -> GPT-5.4-nano -> 云端 qwen2.5 -> 本地cpu。
> 新架构会进一步压缩token成本，原本安装在Haiku上的M2DecisionEngine会被安装在一个更小的模型如GPT-5.4-nano上。
> 文本的展开在云端上的qwen2.5进行，运行速度可以得到大幅提升。
> 因此请将本仓库视为稳定参考版本，而不是最新架构实现。

> English Version：[README.en.md](README.en.md)

Roguelite 叙事游戏引擎，三层 AI 架构驱动。

## 这不是另一个 AI 应用

**让 AI 成为系统内部的语义计算核心，而不只是外挂在程序外部的问答接口。**

`Loombound` 不是最终目标产品，而是一个可运行的垂直 demo——用来验证：如果程序需要长期处理"意义"、"倾向"、"叙事压力"、"后果语义"这类传统软件难以原生表达的状态，系统结构应该如何设计。

**好的分层设计可以极大节省成本、优化运行速度。** → [成本效率](#成本效率) · [运行速度](#运行速度)

之所以选择叙事游戏作为 demo，不是因为目标只是在做游戏，而是因为文字游戏非常适合暴露语义系统真正困难的问题。

→ 如果你只打算先读一个文档，请先读 [LANGUAGE.md](docs/LANGUAGE.md)。

`LANGUAGE.md` 不是术语附录，而是这个项目的核心概念入口。
它定义了 Loombound 如何描述语义层级、处理核心、运行时对象，以及这些东西如何在系统中流动。

→ 完整设想：[docs/SEMANTIC_OS.md](docs/SEMANTIC_OS.md)


## 安装

```bash
git clone https://github.com/HermaeusMorea/Loombound.git
cd Loombound

# 建虚拟环境并安装依赖
python3 -m venv .venv
.venv/bin/pip install -e .

# 配置 API key
cp .env.example .env   # 填入 ANTHROPIC_API_KEY

# 下载本地模型（C1 场景展开用）
ollama pull qwen2.5:7b
```

完成后既可以用 `./loombound`，也可以直接用 `loombound`（需激活 venv：`source .venv/bin/activate`）。

---

## 快速开始

```bash
# 前置条件：.env 里有 ANTHROPIC_API_KEY，ollama 在跑：ollama pull qwen2.5:7b
cp .env.example .env   # 填入 ANTHROPIC_API_KEY

# 1. 一次性全局设置（已有 data/arc_state_catalog.json 则跳过）
./loombound arc-palette

# 2. 生成 saga（Opus 生成图，Haiku 自动生成 scene skeleton，两步合一）
./loombound gen "新加坡地下黑客社区" --lang zh
./loombound gen "太阳帆时代考古调查" --tone "忧郁、诗性、带一点希望感的太空悬疑" --lang zh
./loombound gen "债务猎人逃亡" --worldview "木星轨道殖民地由债务公会和打捞教团共同统治" --lang zh

# 3. 启动游戏（预载路径：Haiku bearing 分类 + qwen2.5:7b 本地展开）
# --lang zh 生成中文场景文字；省略则默认英文
./loombound run --lang zh   # 中文
./loombound run             # English

# 指定 saga
./loombound run --saga hunters_night_yharnam_last_lucid --lang zh

# 测试用：限制 waypoint 数
./loombound run --nodes 2 --lang zh
```

---

## 三层架构

| 阶段 | AI | 做什么 |
|---|---|---|
| **一次性** | Claude Opus（C3） | 生成全局 bearing 枚举（`arc-palette`，~50 条） |
| **每个 saga** | Claude Opus（C3） | 生成 saga 图（waypoint 拓扑、toll lexicon、rules、narration_table） |
| **每个 saga** | Claude Haiku（C2） | 生成 scene skeletons（每 waypoint 场景骨架：scene_concept、选项结构，不含数值） |
| **运行时** | Claude Haiku（C2） | bearing 分类器：每次选择后后台调用 → bearing ID + 下一个 encounter 的 per-option effects + tolls（prompt cache 后 ~$0.0013/次） |
| **运行时** | qwen2.5:7b 本地（C1） | 场景展开：scene skeleton 骨架 + bearing 倾向 → 完整场景散文 |

全程只需要 `ANTHROPIC_API_KEY` + ollama（本地 qwen2.5:7b）。

Opus 仅出现在离线阶段（arc-palette 和 saga 生成），运行时全程 Haiku + qwen2.5:7b。

### 成本效率

三层架构的核心收益是**把高频的运行时场景展开从 API 调用变成本地计算**。

| 方案 | 离线 ×1 | 每局 | 1000 局总计 |
|---|---|---|---|
| **tiered（当前）** Opus gen + Haiku C2 + 本地 C1 | $0.1129 | $0.0148 | **$14.88** |
| 全 Opus（C2 + C1 均换 Opus） | $0.2450 | $0.2199 | $220.11 |
| 全 Haiku（saga gen 也换 Haiku） | $0.0392 | $0.0352 | $35.22 |

实测数据：deep_mine_cult_act1（4 waypoints，8 次选择）。C2 每次选择 ~$0.0019（Haiku cache_read 命中后），随游玩规模扩大离线成本被摊薄。

`./loombound report` 实时输出带 1000 局投影的成本报表。

→ 详细推算：[docs/llm-architecture.md](docs/llm-architecture.md#成本分析)

### 运行速度

利用 prompt cache 的"表格查询"模式后，各阶段的理想延迟：

| 阶段 | 触发时机 | 模型 | 理想延迟 |
|---|---|---|---|
| **arc-palette** | 一次性 | Claude Opus（C3） | 30–90 秒 |
| **saga 生成** | 每个 saga | Claude Opus + Haiku（C3 + C2） | 1–3 分钟 |
| **bearing 分类** | 每次选择（后台） | Claude Haiku（C2，prompt cache 命中） | **1–2 秒** |
| **场景展开** | 每次 encounter（后台预载） | qwen2.5:7b 本地（C1） | **2–10 秒**（有 GPU） |

C2 的 1–2 秒主要是网络往返 + 极短输出（bearing ID 约 10–30 tokens）；prompt cache 命中后无论缓存表格多大延迟都不会增加。C1 在有 GPU 时与 C2 处于同一数量级，两者都在后台运行，玩家通常等不到它们。

**C1 本地速度取决于硬件。** qwen2.5:7b 全精度加载约需 4–5 GB 显存：

| 运行环境 | 速度 | 每场景约需时间 |
|---|---|---|
| GPU（RTX 3060 / 4060 级别） | 20–50 token/s | ~4–10 秒 |
| GPU（RTX 4090 / A100 级别） | 60–100 token/s | ~2–3 秒 |
| CPU 回落（无 GPU 或显存不足） | 2–8 token/s | 16–37 秒 |

作者本地显卡不够格，实测 C1 场景展开在 16–37 秒之间（CPU 推理回落）；日志里的延迟数据反映的是这个条件。换一块能承载 7b 模型的显卡后，C1 延迟将降至 2–10 秒。

**saga 生成的瓶颈是 Haiku，不是 Opus。** 从输出 token 量反推：Opus 生成 saga 图约 ~1,170 tokens（~40 秒），Haiku 生成 scene skeletons 约 ~6,275 tokens（~63 秒）——每个 waypoint 都要完整输出 scene_concept、sanity_axis 和选项结构，6 个 waypoint 累计输出量约是 Opus 的 5×。使用 Haiku 而非更快的模型是主动的成本选择：Haiku 输出费率约为 Opus 的 1/19，且 saga 生成完全可以在开始游玩后台进行——打通一个 saga 通常需要数分钟，生成早已结束。

### 数据文件

| 文件 | 来源 | 内容 |
|---|---|---|
| `data/arc_state_catalog.json` | Claude Opus（一次性） | bearing 枚举（~50 条，运行时 Haiku prompt cache） |
| `data/sagas/<id>.json` | Claude Opus（每 saga） | Saga 图：waypoint 拓扑 + 每 waypoint depth / type / encounters（inlined） |
| `data/sagas/<id>_toll_lexicon.json` | Claude Opus（每 saga） | per-saga toll 词汇表，C2 运行时 cached prefix |
| `data/sagas/<id>_rules.json` | Claude Opus（每 saga） | per-saga 规则集，含 rule.theme keys |
| `data/sagas/<id>_narration_table.json` | Claude Opus（每 saga） | per-saga 叙事主题表（10–15 条，单句心理描述） |
| `data/waypoints/<id>/scene_skeletons.json` | Claude Haiku（每 saga） | 场景骨架：scene_concept、sanity_axis、选项结构（不含 h/m/s 数值） |

> A1 option index（选项结构去掉数值，Haiku 的 per-saga cached prefix）在运行时从 scene skeletons 派生，不单独存文件。

---

## `./loombound` 参数

```bash
./loombound arc-palette                    # 生成全局 bearing 枚举（一次性）
./loombound clean-palette                  # 删除 bearing 枚举

./loombound gen "theme" --lang zh          # 默认：Opus 生图 + Haiku 生 scene skeleton
./loombound gen "theme" --skip-t1-cache    # 只生成 saga 图
./loombound gen "theme" --nodes 8          # waypoint 数（默认 6）
./loombound gen "theme" --tone "..."       # 指定基调
./loombound gen "theme" --worldview "..."  # 指定世界观

./loombound run                            # 启动游戏（自动选最新 saga）
./loombound run --lang zh                  # 中文内容
./loombound run --saga ID                  # 指定 saga
./loombound run --nodes 3                  # 限制 waypoint 数（测试用）
./loombound run --fast MODEL               # 指定 C1 本地模型（默认 qwen2.5:7b）

./loombound report                         # 最新一轮 token 用量 / 成本（含 1000 局投影）
./loombound report --saga ID

./loombound clean --saga ID                # 删除单个 saga 数据
./loombound clean --all                    # 清空所有 saga（保留 bearing 枚举）
./loombound clean-logs                     # 清空 logs/llm.md
```

---

## 前置条件

```bash
cp .env.example .env   # 填入需要的 API key
```

- `ANTHROPIC_API_KEY` — 必须，`gen` 和 `run` 都需要
- ollama 在跑（`ollama serve`），已下载 `ollama pull qwen2.5:7b` — `run` 需要（C1 本地展开）

> **全程只支持 Claude API。** `gen` 使用 Claude Opus（C3）生成 saga 图，`run` 的 C2 分类器使用 Anthropic prompt caching。两者均需要 `ANTHROPIC_API_KEY`。

---

## 日志与报表

LLM 调用记录在 `logs/llm.md`（含每次调用的 token 数、成本、cache 命中情况）。

```bash
./loombound report              # 最新一轮（含离线成本溯源 + 1000 局成本投影）
./loombound report --saga ID
```

---

游戏的 LLM 分层架构（C0/C1/C2/C3 处理核心、A0–A3 数据语义层）设计参考自作者正在进行的另一个项目。
