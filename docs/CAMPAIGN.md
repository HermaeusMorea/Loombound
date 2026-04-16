# 生成 Campaign

## 快速生成

```bash
./gen "你的主题描述"
```

生成完毕后脚本会打印节点图和启动命令。

## 常用参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `theme` | 主题描述（第一个位置参数） | drowned city cult investigation |
| `--nodes N` | 大致节点数 | 6 |
| `--lang zh` | 中文叙事文本 | en |
| `--out NAME` | 输出文件名 | campaign_id（Claude 决定） |
| `--mode preloaded` | 让整份 campaign 在生成时显式看到 Table A，并保存原始 theme/tone/worldview | dynamic |
| `--skip-table-b` | 仅 `./gen preloaded` 可用；跳过自动生成 Table B | 自动生成 |

## 示例

```bash
# 中文渔村主题，8个节点
./gen "渔村诅咒与沉没档案" --nodes 8 --lang zh

# 预载模式：Table A + 用户原始 worldview/tone 一起交给 DeepSeek 生成 campaign，
# 然后自动继续生成该 campaign 的 Table B
./gen preloaded "Singapore shadow net" \
  --model anthropic \
  --tone "humid techno-noir paranoia" \
  --worldview "near-future Singapore corporate black sites and ghost infrastructure"

# 英文灯塔主题，6个节点，指定输出名
./gen "lighthouse keeper's descent" --nodes 6 --out lighthouse_act1
```

## 输出文件

```
data/campaigns/<campaign_id>.json       ← 传给 --campaign 参数
data/nodes/<campaign_id>/<node_id>.json ← 每个节点，arbitrations 是整数（DeepSeek 运行时生成内容）
```

预载模式下，`data/campaigns/<campaign_id>.json` 还会保存一份 `generation_context`，
包括原始 `theme / tone_hint / worldview_hint / generation_mode`，供自动生成的
`Table B` 继续使用，而不是只依赖已经压缩过的 campaign 摘要字段。

当前的预载模型是：

- `Table A`：全局 arc-state catalogue，由 Claude 在运行时分类命中
- `Table B`：按 `node_id` 生成的 scene skeleton，由 DeepSeek 离线生成一次
- 运行时实际生成：Gemma3 混合 `Table B(node)` + `Table A(runtime tendency)` + 当前状态

## 费用估算

每次生成约 $0.02–0.05（Claude Opus，一次调用）。
