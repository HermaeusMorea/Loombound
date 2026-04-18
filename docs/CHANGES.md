# 命名变更记录

glossary 对话中确认的所有命名变更，供后续改代码、文件、注释时查阅。

---

## 数据抽象层级：T → A

| 旧名 | 新名 |
|---|---|
| T0（数据层） | A0 |
| T1（数据层） | A1 |
| T2（数据层） | A2 |
| T3（数据层） | A3 |

---

## 处理核心：T Core → C

| 旧名 | 新名 | 模型 |
|---|---|---|
| T0 Core | C0 | 本地确定性处理器 |
| T1 Core | C1 | gemma3:4b |
| T2 Core | C2 | claude-haiku-4-5 |
| T3 Core | C3 | claude-opus-4-6 |

---

## 领域词

| 旧名 | 新名 |
|---|---|
| campaign | saga |
| node | waypoint |
| arbitration | encounter |
| verdict | toll |
| verdict_dict | toll lexicon |
| arc state | bearing |
| quasi state | tendency |
| floor | depth |
| condition | mark |

---

## 文件重命名（待执行）

| 旧路径 | 新路径 |
|---|---|
| `data/t2_cache_table.json` | `data/a2_cache_table.json` |
| `data/nodes/<id>/t1_cache_table.json` | `data/nodes/<id>/a1_cache_table.json` |
| `data/campaigns/<id>_verdict_dict.json` | `data/campaigns/<id>_toll_lexicon.json` |


---

## 代码标识符（待执行）

| 旧名 | 新名 | 所在位置 |
|---|---|---|
| `t2_cache_table` | `a2_cache_table` | 变量名、方法名、注释 |
| `t1_cache_table` | `a1_cache_table` | 变量名、方法名、注释 |
| `t1_cache_table_index` | `a1_option_index` | 变量名、方法名 |
| `verdict_dict` | `toll_lexicon` | 变量名、JSON 字段 |
| `verdict` | `toll` | 变量名、JSON 字段 |
| `floor` | `depth` | 变量名、JSON 字段 |
| `condition` | `mark` | 变量名、JSON 字段 |
| `M1Store` / `M2Store` | `A1Store` / `A2Store` | 类名 |
| `campaign` | `saga` | 变量名、JSON 字段 |
| `node` | `waypoint` | 变量名、JSON 字段（`node_id` → `waypoint_id` 等） |
| `arbitration` | `encounter` | 变量名、类名、JSON 字段 |

---

## 注意事项

- `floor` 是 Python 内置函数名，改 `depth` 时检查 shadowing
- 文件重命名后需同步更新所有 `glob`、`Path` 引用
