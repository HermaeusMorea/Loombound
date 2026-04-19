# Loombound 架构

---

## 系统主路径

```
arc-palette（一次性）
  C3（Opus）→ arc-state catalog（~50 条 bearing 枚举）

gen（每个 saga）
  C3（Opus）→ saga.json（waypoint 图 + toll lexicon + rules + narration_table）
  C2（Haiku）→ scene_skeletons.json（per-waypoint 场景骨架）

run（游戏会话）
  启动：加载 arc-state catalog + scene skeletons → 构建 C2 classifier
  每个 waypoint：
    PrefetchCache → C1（qwen2.5:7b）预取场景文字
    玩家做选择 → C2（Haiku）fire-and-forget →
      entry_id（bearing 更新）+
      下一个 encounter 的 per-option effects + tolls
  每次 encounter：
    enforce_rule（C2 toll → sanity penalty）
    apply_option_effects（更新 A0 状态）
    PrefetchCache 消费 effects + tolls

report
  解析 logs/llm.md → token 用量 + 1000 局成本对比报表
```

---

## 数据流

```
离线                                   运行时
──────────────────────────────────     ──────────────────────────────────────

C3（Opus）
 └─ saga.json                          加载 saga.json
    waypoints / tone / toll lexicon ──→  RunSession
    rules + narration_table         ──→  RuleSystem
 └─ arc_state_catalog.json            ──→  C2 classifier（全局 cached prefix）

C2（Haiku，离线）
 └─ scene_skeletons.json            ──→  C2 classifier（per-saga cached prefix）
                                        + A1 option index（派生，不落文件）

                                    玩家选择 encounter N
                                       │
                                    C2（Haiku）←── tendency（A0 压缩）
                                       │             arc-state catalog（cached）
                                       │             A1 option index（cached）
                                       │             toll lexicon（cached）
                                       ▼
                                    entry_id + effects + tolls（encounter N+1）
                                       │
                                    PrefetchCache（内存）
                                       │
                                    encounter N+1 渲染时消费
                                       │
                                    enforce_rule → OptionResult（toll + sanity_cost）
                                    apply_option_effects → A0 状态更新
                                       │
                                    narration_table.get(rule.theme) → 单句心理描述
```

---

## 目录结构与模块依赖

规则：**低层不 import 高层**，`runtime/` 是唯一允许 import 全部层的组装点。

```
src/
  runtime/         ← 组装点，import 全部层
    play_cli.py          ← CLI 主循环（_play_waypoint、main）
    play_encounter.py    ← encounter 执行层（_play_encounter、_overlay_effects）
    play_bootstrap.py    ← CLI 启动装配（parse_play_args、build_prefetch_cache）
    saga_loader.py       ← saga 资产加载（LoadedSagaBundle、load_saga_bundle）
    session.py
    play_runtime.py

  t3/              ← C3（Opus）+ A3 数据结构
    core/
      generate_saga.py        ← saga 生成 orchestration
      saga_prompt.py          ← tool schema、_build_user_msg、cost helpers
      saga_validate.py        ← graph 校验（validate_graph、_normalise）
      saga_write.py           ← 落盘（write_saga、print_graph）
      gen_arc_state_catalog.py ← arc-state catalog 生成

  t2/              ← C2（Haiku）+ A2 数据结构
    core/
      m2_decision_engine.py    ← 运行时 bearing 分类器（M2DecisionEngine）
      arc_state.py             ← 后台 bearing 分类线程（ArcStateTracker）
      prefetch.py              ← waypoint 内容预载 facade（PrefetchCache）
      prefetch_seed_merge.py   ← 纯计算：arc-row → tendency、skeleton 合并
      gen_scene_skeletons.py   ← scene skeletons 生成（per-saga）
      collector.py             ← tendency state 构建
      types.py                 ← EncounterSeed、PrefetchEntry、EncounterSlot
    memory/
      a2_store.py              ← arc-state catalog / scene skeletons 加载（RuntimeTableStore）

  t1/              ← C1（qwen2.5:7b）+ A1 数据结构
    core/
      expander.py              ← C1 场景文本展开
      prompts.py               ← C1 prompt 构建
      ollama.py                ← ollama /api/chat transport
    memory/
      scene_history_store.py   ← SceneHistoryStore / SceneHistoryEntry（waypoint 轨迹滑动窗口）

  t0/              ← C0（确定性）+ A0 数据结构
    core/
      enforcement.py           ← toll → sanity_cost 计算
      rule_matcher.py          ← RuleTemplate 匹配
      rule_selector.py         ← 候选规则排序（freshness penalty + priority）
      rule_state.py            ← 运行时规则系统状态（Run / Waypoint 级别）
      context_builder.py       ← EncounterContext 构建
      signals.py               ← encounter 输入的确定性信号提取
      effects.py               ← 选项 effects 应用（health / money / sanity delta）
      cli.py                   ← 终端渲染（HUD、选项、narration）
    memory/
      models.py                ← CoreState、EncounterContext、OptionResult 等核心模型
      types.py                 ← WaypointMemory、WaypointChoiceRecord 等
      encounter.py             ← Encounter 数据结构与生命周期
      run_memory.py            ← RunMemory 操作（update_after_waypoint）
      recording.py             ← 选择记录写回
```

**禁止的方向：**
- `t0/` 不 import `t1/`、`t2/`、`t3/`
- `t1/` 不 import `t2/`、`t3/`
- `t2/` 不 import `t3/`
- 任何层不 import `runtime/`

---

## 信息流方向

| 方向 | 描述 | 实现 |
|---|---|---|
| **自上而下** | 高层核心输出作为低层核心的约束种子 | C3 saga → C2 scene skeleton → C1 展开 |
| **自下而上** | 低层精确状态压缩为高层语言 | A0 精确数值 → tendency → C2（Haiku） |

C2 永远不接触精确整数，只接触倾向带（low/moderate/high）和叙事维度描述。

---

## 关键不变式

1. **toll 由 C2 运行时输出**，scene skeleton 中不存 toll（静态标注不感知玩家状态）
2. **C2 输出 toll 先于 effects 数值**（schema 字段顺序强制），数值必须与 toll 一致
3. **C2 格式验证失败则 retry**（最多 2 次），不降级为确定性规则兜底
4. **PrefetchCache 是唯一的跨-encounter 状态传递通道**（effects + tolls 存内存，不落文件）
5. **narration_table 由 C3 per-saga 生成**（10–15 条，单句心理描述），rule.theme 必须是其中的 key

