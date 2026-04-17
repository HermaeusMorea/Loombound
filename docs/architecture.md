# Loombound 架构

---

## 系统主路径

```
arc-palette（一次性）
  Opus → T2 cache table（~50 条 arc-state 枚举）

gen（每个 campaign）
  Opus → campaign.json（节点图 + verdict_dict）
  Haiku → t1_cache_table.json（per-node 场景骨架）

run（游戏会话）
  启动：加载 T2 cache table + T1 cache table → 构建 M2Classifier
  每个节点：
    PrefetchCache → Fast Core（gemma3）预取场景文字
    玩家做选择 → M2（Haiku）fire-and-forget →
      entry_id（arc state 更新）+
      下一个 arb 的 per-option effects + verdicts
  每次 arbitration：
    enforce_rule（M2 verdict → sanity penalty）
    apply_option_effects（更新 M0 状态）
    PrefetchCache 消费 effects + verdicts

report
  解析 logs/llm.md → token 用量报表
```

---

## 数据流

```
离线                                 运行时
────────────────────────────────     ──────────────────────────────────────

Opus
 └─ campaign.json                    加载 campaign.json
    nodes / tone / verdict_dict  ──→  RunSession
 └─ t2_cache_table.json          ──→  M2Classifier（全局 cached prefix）

Haiku（离线）
 └─ t1_cache_table.json          ──→  M2Classifier（per-campaign cached prefix）
                                      + T1 option index（派生，不落文件）

                                  玩家选择 arb N
                                     │
                                  M2（Haiku）←── quasi state（M0 压缩）
                                     │            T2 cache table（cached）
                                     │            T1 option index（cached）
                                     │            verdict_dict（cached）
                                     ▼
                                  entry_id + effects + verdicts（arb N+1）
                                     │
                                  PrefetchCache（内存）
                                     │
                                  arb N+1 渲染时消费
                                     │
                                  enforce_rule → OptionResult（verdict + sanity_cost）
                                  apply_option_effects → M0 状态更新
```

---

## 模块依赖方向

规则：**下层不 import 上层**，`runtime/play_cli` 是唯一允许 import 全部模块的组装点。

```
scripts/
  generate_campaign.py
  gen_t1_cache_table.py      ← play_cli 不 import；仅 generate_campaign 调用
  gen_t2_cache_table.py
  report_llm_usage.py
  build_demo.py
        │
        ▼（单向）
src/core/
  runtime/play_cli            ← 组装点，import 全部
    ├─ runtime/session, campaign
    ├─ llm_interface/         ← M2Classifier, FastCore, PrefetchCache, collector
    │    └─ memory/           ← RunMemory, NodeMemory, M1Store, M2Store
    │         └─ deterministic_kernel/   ← 数据模型（无 import）
    ├─ enforcement/
    │    └─ deterministic_kernel/
    ├─ rule_engine/
    │    └─ deterministic_kernel/
    ├─ signal_interpretation/
    │    └─ deterministic_kernel/
    ├─ state_adapter/
    │    └─ deterministic_kernel/
    ├─ narration/
    ├─ authoring/
    └─ presentation/
```

**禁止的方向：**
- `src/` 不 import `scripts/`（现在 `generate_campaign.py` import `gen_t1_cache_table` 是待修的违规）
- `deterministic_kernel` 不 import 任何 `src/core` 上层模块
- `memory` 不 import `llm_interface` 或 `runtime`

---

## 信息流方向

| 方向 | 描述 | 实现 |
|---|---|---|
| **自上而下** | 高层 AI 输出作为低层 AI 的约束种子 | Opus campaign → Haiku T1 cache → Fast Core 展开 |
| **自下而上** | 低层精确状态压缩为高层语言 | M0 精确数值 → quasi state → M2 Haiku |

M2 永远不接触精确整数，只接触倾向带（low/moderate/high）和叙事维度描述。

---

## 关键不变式

1. **verdict 由 M2 运行时输出**，T1 cache 中不存 verdict（静态标注不感知玩家状态）
2. **M2 输出 verdict 先于 h/m/s**（schema 字段顺序强制），数值必须与 verdict 一致
3. **M2 格式验证失败则 retry**（最多 2 次），不用 T0 tag-matching 兜底
4. **PrefetchCache 是唯一的跨-arbitration 状态传递通道**（effects + verdicts 存内存，不落文件）
5. **scripts 只是入口**，业务逻辑属于 `src/`（待完成：`gen_t1_cache_table` 迁移）
