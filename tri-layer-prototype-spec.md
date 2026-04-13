# PRISM：原型实现规范

PRISM 是一种用于 AI 驱动实时内容系统的通用架构，解决的核心问题是：

**如何让一个需要 AI 生成内容的系统在运行时几乎没有加载感，同时保持状态管理
的严格性和可验证性。**

适用场景：任何具备以下特征的系统——
- 有离散的节点结构（关卡、房间、事件、场景）
- 节点内用户参与时间 > AI 生成时间
- 内容可以模板化（AI 提供参数，引擎实例化资产）

---

## PRISM 的构成

PRISM 由**三个组件**、**两条协议通道**和**节点系统**构成。
三个组件负责分工，两条协议通道负责翻译，节点系统告诉 PRISM 何时触发预载。

### 三个组件

```
┌─────────────────────────────────────┐
│           Slow Core                 │
│        （远程 AI，慢速核心）          │
│                                     │
│  语言：quasi（倾向、语义方向）         │
│  职责：长程规划，生成未来节点的倾向    │
│  特征：慢（5-15s）/ 贵 / 异步        │
└──────────────┬──────────────────────┘
               │
          协议通道 A
      Fast Core 做双向翻译
               │
┌──────────────▼──────────────────────┐
│           Fast Core                 │
│        （本地 AI，快速核心）          │
│                                     │
│  语言：quasi ↔ 精确，双向转换        │
│  职责：Collector 上行 / Generator 下行│
│  特征：中速 / 低成本 / 协议转换       │
└──────────────┬──────────────────────┘
               │
          协议通道 B
      Fast Core 做双向翻译
               │
┌──────────────▼──────────────────────┐
│             Kernel                  │
│          （确定性核心）               │
│                                     │
│  语言：精确（整数、合法 schema）       │
│  职责：状态维护，验收所有进入的内容    │
│  特征：极快 / 零成本 / 严格验证       │
└─────────────────────────────────────┘
```

Slow Core 和 Kernel 不直接通信。强行让它们直接对话会导致：
- Kernel 被迫接受模糊输入 → 验证失效
- Slow Core 被迫处理精确数值 → 数值在其返回前已过期，失去意义

### 两条协议通道

**协议通道 A（Fast Core ↔ Slow Core）**

协议通道 A 本质上是一个 codec，Fast Core 的两个子角色分别承担两个方向：

| 方向 | 角色 | 内容 | 处理方式 |
|---|---|---|---|
| 上行（→ Slow Core）| Collector（Encoder）| CoreState 数值 + 历史记录 | 压缩为倾向带 + 语义摘要 |
| 下行（← Slow Core）| Generator（Decoder）| 未来节点的 quasi 倾向和结构 | 结合当前状态展开为具体内容 |

上行目标：**保精确**——倾向和语义必须如实反映当前状态，不能失真。
下行目标：**保互动**——展开时根据实际上下文做戏剧性调节，不是死板查表。

Decoder 不是对称解压：Generator 展开时需要结合 Phase 1 的实际结果做 delta 调和，
是**上下文敏感的解码**，不是原样还原 Slow Core 的意图。

**协议通道 B（Fast Core ↔ Kernel）**

| 方向 | 角色 | 内容 | 处理方式 |
|---|---|---|---|
| 上行（← Kernel）| Collector（读取端）| CoreState 精确数值 | Collector 读取，离散化后打包，经协议通道 A 上行 |
| 下行（→ Kernel）| Generator（写入端）| 展开后的结构化内容 | Generator 提交，Kernel 验收，验证职责属于 Kernel |

### 节点系统

节点系统是 PRISM 实现预载的前提，没有它三个组件只能同步运行。

**节点**是系统的离散执行单元（关卡、房间、事件），每个节点内部分为两个阶段：

```
节点 N
  ├─ Phase 1（关键阶段）
  │   定义：该阶段的行为结果会影响 Slow Core 对后续节点的规划
  │   期间：Generator 持续监听 Slow Core 发来的节点 N+1 quasi 描述
  │          （Slow Core 在上一循环 N-1 Phase 1 结束时已被触发）
  │          Collector 同步记录 Phase 1 期间的状态变化
  │   结束条件满足（Generator 已收到 N+1 quasi 且 Phase 1 已结束）→ 并发触发：
  │     · Collector：将记录的 Phase 1 状态打包上行给 Slow Core，
  │       Slow Core 开始异步生成节点 N+2 的 quasi 描述
  │     · Generator：结合收到的节点 N+1 quasi 描述与
  │       Phase 1 实际结果，开始生成完整的节点 N+1 内容
  │
  └─ Phase 2（缓冲阶段）
      定义：该阶段的行为结果不改变 Slow Core 正在进行的预生成所依赖的状态
      作用：同时为两件事提供时间窗口——
            Generator 在后台完成节点 N+1 的生成；
            Slow Core 异步处理节点 N+2 的 quasi 描述
      形式：可以是被动叙述，也可以是真实战斗或任何主动游玩——
            边界是信息重要性，不是玩家活动类型
```

**两个阶段的边界是信息边界，不是活动边界。**
Phase 2 可以是真实游玩，玩家感知不到任何阶段切换。

这套节点分类告诉 PRISM：
- **何时上行**：Generator 收到 N+1 quasi 且 Phase 1 结束 → Collector 打包状态上行给 Slow Core
- **何时展开**：同上触发 → Generator 开始；Phase 2 结束前完成 N+1 节点生成
- **何时可用**：进入节点 N+1 时 → N+1 的内容已就绪，零等待

唯一无法预载的是系统启动时的第一个节点，需要同步生成，这是 PRISM
架构下唯一不可回避的等待点。

---

## 关键抽象

### CoreState（精确状态）

Kernel 维护并**可直接处理**的精确系统状态——只包含 Kernel 能读写、计算、验收的字段。

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class CoreState:
    """Kernel 拥有并维护的精确系统状态。Kernel 可对所有字段做验证和 delta 计算。"""
    health: int = 10
    max_health: int = 10
    resource_a: int = 5      # 金币、能量、等等
    resource_b: int = 6      # 理智、士气、等等
    floor: int = 1
    act: int = 1
```

### MetaState（叙事状态）

Kernel **存储**但**无法语义处理**的叙事性数据。Kernel 只把它当 blob 保存和传递，
无法理解其含义——语义解读由 Fast Core（本地 LLM）完成。

```python
@dataclass(slots=True)
class MetaState:
    """
    叙事层状态。Kernel 仅存储，不做语义计算。
    由 Fast Core 读取后解读，生成 QuasiMetaState 发给 Slow Core。
    """
    active_conditions: list[str] = field(default_factory=list)
    narrator_tone: dict[str, int] = field(default_factory=dict)  # 原始计数器
    theme_bias: dict[str, int] = field(default_factory=dict)     # 原始计数器
    behavior_counters: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

**CoreState 与 MetaState 的分工**：

| | CoreState | MetaState |
|---|---|---|
| Kernel 能否处理 | 是（整数加减、阈值判断、验收） | 否（只存 raw 数据，不解读） |
| 向上翻译方式 | 确定性代码 → QuasiCoreState | 本地 LLM → QuasiMetaState |
| 典型字段 | health、money、floor、act | narrator_tone、theme_bias、active_conditions |

### QuasiCoreState（倾向状态）

中介层向上翻译的结果，供 Core LLM 消费。全部为离散化倾向值，不含精确数字。

```python
from typing import Literal

HealthBand    = Literal["critical", "low", "medium", "high"]
ResourceBand  = Literal["scarce", "low", "medium", "abundant"]
ToneBand      = Literal["none", "low", "medium", "high"]

@dataclass(slots=True)
class QuasiCoreState:
    """离散化的倾向状态，供 Core LLM 规划使用。"""
    health: HealthBand
    resource_a: ResourceBand
    resource_b: HealthBand
    active_conditions: list[str]
    pressure_tags: list[str]        # 语义压力标签，如 "high_occult_exposure"
    arc_momentum: str               # 当前弧线动量，如 "destabilizing"
```

**重要**：CoreState → QuasiCoreState 的转换是**纯确定性代码**，不经过 LLM：

```python
def discretize_core_state(state: CoreState) -> QuasiCoreState:
    """纯阈值映射，无 LLM 参与。"""
    def health_band(v: int, max_v: int) -> HealthBand:
        ratio = v / max_v if max_v > 0 else 0
        if ratio <= 0.2:  return "critical"
        if ratio <= 0.5:  return "low"
        if ratio <= 0.8:  return "medium"
        return "high"

    def resource_band(v: int) -> ResourceBand:
        if v <= 2:   return "scarce"
        if v <= 5:   return "low"
        if v <= 8:   return "medium"
        return "abundant"

    return QuasiCoreState(
        health=health_band(state.health, state.max_health),
        resource_a=resource_band(state.resource_a),
        resource_b=health_band(state.resource_b, 10),  # 假设上限 10
        active_conditions=list(state.active_conditions),
        pressure_tags=[],   # 由中介 LLM 根据 conditions 生成
        arc_momentum="stable",  # 由中介 LLM 根据历史生成
    )
```

### QuasiMetaState（语义摘要）

中介层对历史事件和叙事状态的语义压缩，供 Core LLM 理解弧线上下文。

```python
@dataclass(slots=True)
class QuasiMetaState:
    """叙事层的语义摘要，由本地 LLM 从原始历史数据生成。"""
    arc_so_far: str              # 玩家行为弧线的自然语言摘要
    dominant_themes: list[str]   # 主导主题标签
    tone: dict[str, ToneBand]    # 叙事气氛倾向带（不是精确计数器）
    key_events: list[str]        # 最重要的历史事件列表
```

**重要**：这里的 `tone` 虽然来自 Kernel 内部的精确计数器，发给 Core LLM 前
同样要离散化为倾向带，不能原样透传数字。

### GenerationJob

流水线中的基本调度单元。

```python
from typing import Literal
import uuid

JobKind   = Literal["node_seed", "room_seed", "event_seed", "summary"]
JobStatus = Literal["pending", "running", "ready", "failed", "stale"]

@dataclass
class GenerationJob:
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: JobKind = "node_seed"
    status: JobStatus = "pending"
    priority: int = 1              # 0=P0阻塞, 1=P1后台, 2=P2低优先级
    quasi_input: dict = field(default_factory=dict)   # 发给 Core LLM 的输入
    quasi_output: dict | None = None                  # Core LLM 返回的结果
    resolved_output: dict | None = None               # 本地展开后的完整内容
    error: str = ""
    metadata: dict = field(default_factory=dict)
```

### SeedPack 和 ResolvedPack

```python
@dataclass
class SeedPack:
    """Core LLM 的输出：高密度结构化种子，不含完整散文。"""
    kind: JobKind
    payload: dict        # quasi 级别的内容骨架
    metadata: dict = field(default_factory=dict)

@dataclass
class ResolvedPack:
    """本地 LLM 展开后的完整内容，可直接提交 Kernel 验收。"""
    kind: JobKind
    payload: dict        # 展开后的完整结构，含具体数值和文字
    metadata: dict = field(default_factory=dict)
```

---

## 翻译规则

### 向上翻译（Kernel → Core LLM）

目标：**最大化倾向与语义的精确度**。不传精确数值，因为数值时效性太短；
但传递的倾向和语义摘要必须如实反映系统状态。

| 数据类型 | 来源 | 处理方式 |
|---|---|---|
| CoreState 数值字段 | Kernel 直接读取 | 确定性代码离散化为倾向带 → QuasiCoreState |
| MetaState 计数器（tone、theme_bias 等）| Kernel 存储的 raw 数据 | 本地 LLM 语义解读，离散化为倾向带 → QuasiMetaState |
| 历史事件列表 | Memory | 本地 LLM 语义压缩为 arc_so_far / key_events |
| 叙事弧线状态 | 历史记录推断 | 本地 LLM 语义摘要 → QuasiMetaState |

打包后由 Kernel 确认数据来源正确，再发送给 Slow Core。

### 向下翻译（Core LLM → Kernel）

目标：**产生与当前场景的互动感**，而不是死板地执行 Core LLM 的意图。

本地 LLM 接收 Core LLM 的 quasi 输出，结合当前实际系统状态，做**上下文敏感
的转换**：

- 同样的 `tendency: "health_negative"`，在玩家血量充裕时转换为 `-1`，
  在玩家濒死时可以转换为更戏剧性的数值
- 同样的 `"healing_option_available": true`，在玩家危急时可以设置更大的恢复量

**转换自由在 Kernel 允许的 delta 范围内行使。** Kernel 验收最终数值，
不接受超出范围的值——软转换在硬边界内。

最终结构化输出提交 Kernel 验收，**验证职责属于 Kernel，不属于中介 LLM**。

---

## 预载机制

### 节点前后段设计

```
节点 N（任意节点）
  ├─ 前段（Phase 1）：影响未来状态的关键行为
  │   └─ Generator 监听 Slow Core 发来的 N+1 quasi
  │   └─ Collector 记录 Phase 1 期间的状态变化
  │   └─ [quasi 已到 + Phase 1 结束] → 并发触发，无等待：
  │        Collector 上行 → Slow Core 开始生成 N+2 quasi
  │        Generator 启动 → 结合 N+1 quasi + 前段实际结果，开始生成 N+1
  │
  └─ 后段（Phase 2）：结果已大致确定，不影响 Core LLM 正在进行的预生成
      └─ 可以是被动叙述，也可以是主动但无宏观影响的游玩
      └─ [期间] Generator 在后台完成节点 N+1 的生成
```

**关键**：前后段的边界是**信息重要性的边界，不是游玩活动的边界**。
后段可以是真实战斗、探索、任何形式的游玩，只要其结果不改变已经启动的
预生成所依赖的关键状态。

### 优先级分层

| 优先级 | 场景 | 策略 |
|---|---|---|
| P0 | 当前节点内容缺失 | blocking 生成 + 流式输出 |
| P1 | 下一节点内容 | 后台排队，节点进入时触发 |
| P2 | 未来分支节点 | 低优先级后台 |
| P3 | 历史总结、meta 更新 | 节点结束后异步 |

### delta 调和

Core LLM 生成 N+2 时，N+1 还未发生，只能基于预测。当 N+1 实际结果与预测
偏差较大时，本地 LLM 在最终展开 N+2 时需要做修正：

```python
delta = actual_quasi_state - predicted_quasi_state
# 本地 LLM 根据 delta 调整内容侧重，而非重新规划整体结构
```

---

## Python 原型组件结构

```
tri_layer/
├── kernel/
│   ├── state.py          # CoreState 定义和状态机逻辑
│   ├── validator.py      # 验收所有进入 Kernel 的内容
│   └── discretizer.py    # 确定性代码：CoreState → QuasiCoreState
│
├── intermediary/
│   ├── collector.py      # Collector：Phase 1 结束时上行打包，发给 Slow Core
│   ├── generator.py      # Generator：Phase 1 结束时下行展开，生成 N+1 节点内容
│   └── summarizer.py     # 本地 LLM：MetaState → QuasiMetaState（供 Collector 调用）
│
├── core_llm/
│   ├── client.py         # Core LLM API 调用（tool use / structured output）
│   └── prompts.py        # 各 job kind 的 prompt 模板
│
├── pipeline/
│   ├── jobs.py           # GenerationJob 定义
│   ├── scheduler.py      # P0/P1/P2/P3 优先级队列
│   └── cache.py          # 内容缓存 + 过期检测
│
├── content/
│   ├── seed_pack.py      # SeedPack 定义
│   ├── resolved_pack.py  # ResolvedPack 定义
│   └── templates.py      # 内容模板（引擎实例化的基础）
│
└── runtime/
    └── node.py           # 节点生命周期：前段/后段触发逻辑
```

### 核心接口契约

```python
# kernel/validator.py
class Kernel:
    def validate_and_apply(self, resolved_pack: ResolvedPack) -> bool:
        """验收中介层提交的内容。返回是否通过。"""
        ...

    def get_core_state(self) -> CoreState:
        """提供当前精确状态供中介层读取。"""
        ...

# intermediary/collector.py
class Collector:
    def collect(self, core_state: CoreState, meta_state: MetaState, history: list) -> dict:
        """
        Phase 1 结束时触发。
        CoreState → QuasiCoreState：确定性代码，无 LLM。
        MetaState + history → QuasiMetaState：本地 LLM 语义摘要。
        返回可直接发给 Slow Core 的 quasi 输入包。
        """
        quasi_core = discretize_core_state(core_state)                       # 纯代码
        quasi_meta = self.summarizer.summarize(meta_state, history)           # 本地 LLM
        return {"quasi_core": quasi_core, "quasi_meta": quasi_meta}

# intermediary/generator.py
class Generator:
    def generate(
        self,
        seed_pack: SeedPack,        # Slow Core 返回的下一节点 quasi 描述
        phase1_state: CoreState,    # Phase 1 实际结束状态（用于 delta 调和）
        allowed_ranges: dict,
    ) -> ResolvedPack:
        """
        Phase 1 结束时触发，与 Collector 并发。
        本地 LLM 上下文敏感展开：结合 quasi 描述与 Phase 1 实际结果。
        phase1_state 用于 delta 调和，allowed_ranges 是 Kernel 的 delta 边界。
        """
        ...

# pipeline/scheduler.py
class Pipeline:
    async def request_content(
        self,
        kind: JobKind,
        context: dict,
        priority: int = 1,
    ) -> ResolvedPack:
        """
        P0（priority=0）：blocking 等待，支持流式输出。
        P1/P2：后台排队，完成后写入缓存。
        """
        ...
```

---

## 实现顺序建议

**第一步：Kernel + 离散化**
先把 `CoreState`、`discretize_core_state()`、`Kernel.validate_and_apply()` 写好。
这是整个系统的地基，必须稳固。可以用简单的 dict 替代 LLM 先跑通验证逻辑。

**第二步：Core LLM client**
实现 `core_llm/client.py`，用 Anthropic API + tool use 拿结构化 `SeedPack`。
先写一个 job kind（如 `node_seed`），跑通端到端调用。

**第三步：DownwardTranslator（P0 路径）**
实现最简版的向下翻译：本地 LLM 把 `SeedPack` 展开为 `ResolvedPack`，提交
Kernel 验收。P0 阻塞路径跑通后，基本的内容生成闭环就完整了。

**第四步：UpwardTranslator**
实现 `summarizer.py`（本地 LLM 总结历史），再实现完整的向上翻译打包。
此时 Core LLM 开始接收真实的上下文，而不是空 payload。

**第五步：Scheduler + 预载**
实现优先级队列和后台生成。节点进入时触发 P1 预生成，节点后段时完成展开。
缓存命中率达到目标后，加载感基本消失。

**第六步：流式输出（P0 降级）**
为 P0 阻塞情况加流式输出，把等待感转化为阅读/观察体验。

---

## 关键设计原则速查

1. **不同层使用不同语言** — 精确层和语义层之间必须有专门翻译机制
2. **AI 层处理倾向，确定性层处理数值** — LLM 给方向，Kernel 决定数字
3. **发给 AI 的粒度匹配 AI 的时间尺度** — 异步返回的 LLM 只接收在其延迟内稳定的倾向描述
4. **在确定性窗口内完成 AI 生成** — 利用玩家参与时间藏住生成延迟
5. **预测偏差是常态** — 设计要支持局部修正，由中介 LLM 在语义层完成
6. **上行保精确，下行保互动** — 上行如实反映状态，下行根据上下文产生戏剧性
7. **前后段边界是信息边界** — 后段可以是真实游玩，只要不影响正在进行的预生成
8. **模板化是零加载的前提** — AI 只提供参数，引擎实例化资产

---

## 依赖建议

```
anthropic          # Core LLM API（tool use / structured output）
ollama 或 llama-cpp-python  # 本地中介 LLM
pydantic           # schema 验证（Kernel 验收层）
asyncio            # 后台预生成调度
```

Core LLM 调用建议使用 Anthropic tool use，定义严格的 tool schema 对应每种
`JobKind`，让 LLM 填参数而不是生成自由文本。这是保证 `SeedPack` 结构合规的
最可靠方式。
