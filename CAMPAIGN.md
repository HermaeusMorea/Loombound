# 生成 Campaign

## 快速生成

```bash
python generate_campaign.py "你的主题描述"
```

生成完毕后脚本会打印节点图和启动命令。

## 常用参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `theme` | 主题描述（第一个位置参数） | drowned city cult investigation |
| `--nodes N` | 大致节点数 | 6 |
| `--lang zh` | 中文叙事文本 | en |
| `--out NAME` | 输出文件名 | campaign_id（Claude 决定） |

## 示例

```bash
# 中文渔村主题，8个节点
python generate_campaign.py "渔村诅咒与沉没档案" --nodes 8 --lang zh

# 英文灯塔主题，6个节点，指定输出名
python generate_campaign.py "lighthouse keeper's descent" --nodes 6 --out lighthouse_act1
```

## 输出文件

```
data/campaigns/<campaign_id>.json       ← 传给 --campaign 参数
data/nodes/<campaign_id>/<node_id>.json ← 每个节点，arbitrations 是整数（DeepSeek 运行时生成内容）
```

## 费用估算

每次生成约 $0.02–0.05（Claude Opus，一次调用）。
