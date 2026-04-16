# loombound

`loombound` 是一个运行在 CLI 中的文字冒险 / 跑团风格原型游戏。

它当前的目标是先验证一套稳定的游戏结构：

- 以决定论为优先的裁决内核
- `Run -> Node -> Arbitration` 的运行时模型
- `RunMemory / NodeMemory` 的双层记忆
- LLM 负责生成内容资产、预载后续内容并参与提议，kernel 负责状态与合法更新
- 一个真正可玩的终端 HUD 式体验

## 游戏是什么

这个项目当前可以理解成一个带有克苏鲁式心智压力主题的命令行叙事游戏。

游戏场景分为两层：

1. 全局大地图  
玩家在地图上推进，并决定下一个要进入哪个节点。

2. 地图节点 `Node`  
每个节点代表一个局部场景，例如遭遇、调查、交易、仪式、异象或事件链。

玩家在地图上选择下一个节点后，会进入该节点，并在节点内经历一个或多个事件选择。

## 核心玩法循环

当前设计中的完整流程是：

1. 初始化一局 `Run`
2. 在全局地图上选择下一个 `Node`
3. 进入 `Node`
4. 节点内触发一个或多个 `Arbitration`
5. 玩家在每个 `Arbitration` 中做出选择
6. 系统根据规则裁决结果更新状态
7. 节点结束后，将 `NodeMemory` 提炼并写入 `RunMemory`
8. 回到全局地图，继续下一节点

这里的 `Arbitration` 就是“当前一次需要玩家选择，也需要系统给出裁决的场景”。

## CLI HUD

当前主入口已经不是单次 demo，而是一个可玩的 CLI loop：

- 顶部固定 HUD：显示当前页面、`Health`、`Money`、`Sanity`
- 中间内容区：显示当前 node、arbitration 或结算结果
- 底部输入区：显示当前输入提示

界面目前使用 ANSI 颜色和盒状布局实现，并且在窄终端下会自动从双栏切成上下堆叠，以减少边框断裂和换行错位。

## 状态系统

系统当前区分两层状态：

### `CoreState`

`CoreState` 是结构化、决定论、立即生效的状态，例如：

- `health`
- `money`
- `sanity`
- `inventory / tags`
- `current location`

这类状态由 kernel 严格维护与更新。

### `MetaState`

`MetaState` 是更偏解释层、叙事层、长期心理层的状态，例如：

- 遭遇过的重大事件
- 创伤
- 执念
- 恐惧偏向
- 人物当前的叙事印象

这类状态可以保留结构化字段，也可以包含由 LLM 解释和整理的文本性描述。

## 运行时架构

项目当前采用以下运行时模型：

- `Run`
  - 表示一整局游戏
  - 持有全局状态、全局规则系统、全局记忆

- `Node`
  - 表示地图上的一个节点
  - 持有节点内局部记忆与节点级规则状态

- `Arbitration`
  - 表示节点内一次需要裁决的事件选择
  - 持有 `Arbitration.context`、options、result 与状态

- `RunMemory`
  - 跨节点长期存在
  - 记录长期记忆、主题计数、行为计数、重大事件与 narrator mood

- `NodeMemory`
  - 只在当前节点内存在
  - 节点结束后提炼摘要写入 `RunMemory`

## 模块划分

当前仓库按十一个核心模块组织：

1. `deterministic_kernel`
2. `state_adapter`
3. `signal_interpretation`
4. `rule_engine`
5. `enforcement`
6. `llm_interface`
7. `presentation`
8. `narration`
9. `memory`
10. `authoring`
11. `runtime`

其中：

- `runtime` 负责 `Run / Node / Arbitration` 生命周期
- `state_adapter` 负责把手写资产与 LLM 生成内容装配成内部运行时对象
- `rule_engine` 负责规则匹配、选择与规则运行时状态
- `llm_interface` 负责远程主生成、本地补位与结构化 LLM 输出边界
- `presentation` 负责 CLI 展示布局与输出格式
- `memory` 负责 `RunMemory / NodeMemory`
- `narration` 负责文字演出
- `authoring` 负责规则、文本模板与内容资产

## LLM 在项目中的角色

LLM 是当前项目中的必需层，但它不直接替代 kernel。

它当前承担这些核心职责：

- 自动生成结构化内容资产
- 根据已有 `RunMemory` 预生成后续节点与 arbitration 的信息
- 为 node 内的每次 `Arbitration` 预生成事件素材、候选效果描述与 rule bias 提议
- 在节点内基于已经确定的裁决结果生成文字演出
- 整理 `MetaState` 与 memory summary

这些内容进入程序时，应该优先经过 `state_adapter`：

- authored JSON
- LLM rule packs
- LLM node packs
- LLM arbitration packs
- LLM narration packs
- LLM effect / meta proposals

这样 kernel 内部始终只处理统一、可验证的运行时对象，而不是直接处理自由文本。

也就是说：

- kernel 决定结构、状态、规则、合法更新
- LLM 负责世界细节、气氛、文本表现与部分预生成内容

## 当前仓库状态

当前 repo 已经能够：

- 运行一个带地图选择与节点内多次裁决的可玩 CLI loop
- 以决定论方式对选项给出 `stable / destabilizing` 裁决
- 输出 `sanity_cost` 与 `sanity_delta`
- 以分区 HUD 的方式显示当前状态、场景与选项
- 在窄终端下自动回退为更稳定的上下布局

当前 repo 还没有：

- 图形界面
- 完整的 LLM 接口实现
- 最终世界观文本定稿

## 运行

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m src.core.runtime.play_cli
```

## 当前方向

接下来的重点是：

- 继续打磨 CLI 玩法 loop
- 继续打磨 CLI HUD 与输入体验
- 接入 LLM 生成内容资产与结构化提议接口
- 完善 `Run / Node / Arbitration` 的内容生成与裁决体验
- 让 `MetaState` 与 LLM 的角色更清晰
- 逐步把原型推进成可玩的命令行叙事跑团游戏
