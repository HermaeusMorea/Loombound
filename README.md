# li-director-sts2

`li-director-sts2` 是一个面向原型阶段的 Python 仓库，用于验证“Slay the Spire 2 风格的 AI 礼官导演系统”是否可行。

当前目标不是制作正式 mod，也不是让 AI 替玩家求解最优策略，而是先做三件事：

1. 把局面表示成稳定、可验证的外部 `Arbitration` 输入
2. 用预定义规则模板对选项做“守礼 / 违礼”判断
3. 生成可选的礼制旁白，并记录 `ritual_collapse` 与轻量 run memory

## 当前范围

- 文档优先：先明确问题定义、MVP 边界、规则系统结构
- 原型优先：先跑通离线 demo，不接入真实游戏 API
- 决定论优先：规则选择与执行尽量稳定、可调试、可测试
- 文案可选：旁白系统可关闭，未来可替换为 LLM 或模板混合方案
- 当前仓库以 deterministic kernel 为核心原型，但长期设计上为更深入的 LLM 导演接入预留接口
- 系统长期上将演化为带有 run 内记忆的礼官导演系统
- 系统长期上定位为叠加在原生流程之上的 overlay ritual judge，而不是替换原生状态机

补充文档说明：

- `docs/master-plan.md` 保存完整设计蓝图与长期路线
- `docs/decision-log.md` 记录关键架构与产品决策

## 目录

- `docs/`: 项目定义、范围、风格规范、架构、路线图
- `data/`: 样例上下文、规则模板、旁白模板
- `schemas/`: JSON schema 与结构说明
- `src/`: 最小核心引擎与 CLI demo
- `tests/`: 规则选择与执行的基础测试
- `tasks/`: 近期执行计划与 backlog

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m src.core.runtime.cli
python -m src.core.runtime.cli --context data/sample_contexts/shop/shop_01.json
python -m src.core.runtime.run_memory_demo --no-input
```

如果未激活虚拟环境，也可以直接使用：

```bash
.venv/bin/python -m src.core.runtime.cli
```

多节点、带全局 `RunMemory` 的 demo：

```bash
.venv/bin/python -m src.core.runtime.run_memory_demo --no-input
.venv/bin/python -m src.core.runtime.run_memory_demo --node data/sample_nodes/combat_rewards_01.json --node data/sample_nodes/shop_01.json --choice card_1 --choice plain_idol --choice buy_potion
```

read-only 观察适配 demo：

```bash
.venv/bin/python -m src.core.runtime.observe_demo --no-narration
```

当前仓库没有强制第三方运行时依赖。`pytest` 尚未内置安装；如需运行测试，请在可联网环境中额外安装它。

## 原型原则

- AI 不直接替玩家做最优决策
- 当前默认模式下，规则主要来自预定义模板，而不是自由生成
- 规则必须可执行、可验证、可调试
- 第一版只覆盖战斗外决策
- 第一版只做软惩罚，不做硬锁

## 下一步

建议先按以下顺序阅读：

1. `docs/project-definition.md`
2. `docs/mvp-scope.md`
3. `docs/master-plan.md`
4. `docs/decision-log.md`
5. `docs/system-architecture.md`
6. `docs/style-bible.md`
7. `tasks/module-progress.md`
