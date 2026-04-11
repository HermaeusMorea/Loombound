# li-director-sts2

`li-director-sts2` 是一个面向原型阶段的 Python 仓库，用于验证“Slay the Spire 2 风格的 AI 礼官导演系统”是否可行。

当前目标不是制作正式 mod，也不是让 AI 替玩家求解最优策略，而是先做三件事：

1. 把局面表示成稳定、可验证的外部 `choice context`
2. 用预定义规则模板对选项做“守礼 / 违礼”判断
3. 生成可选的礼制旁白，并记录 `ritual_collapse`

## 当前范围

- 文档优先：先明确问题定义、MVP 边界、规则系统结构
- 原型优先：先跑通离线 demo，不接入真实游戏 API
- 决定论优先：规则选择与执行尽量稳定、可调试、可测试
- 文案可选：旁白系统可关闭，未来可替换为 LLM 或模板混合方案

## 目录

- `docs/`: 项目定义、范围、风格规范、架构、路线图
- `data/`: 样例上下文、规则模板、旁白模板
- `schemas/`: JSON schema 与结构说明
- `src/`: 最小核心引擎与 CLI demo
- `tests/`: 规则选择与执行的基础测试
- `tasks/`: 近期执行计划与 backlog

## 快速开始

```bash
python -m src.demo.cli
python -m src.demo.cli --context data/sample_contexts/shop/shop_01.json
pytest
```

## 原型原则

- AI 不直接替玩家做最优决策
- 规则主要来自预定义模板，不依赖 LLM 自由发明
- 规则必须可执行、可验证、可调试
- 第一版只覆盖战斗外决策
- 第一版只做软惩罚，不做硬锁

## 下一步

建议先按以下顺序阅读：

1. `docs/project-definition.md`
2. `docs/mvp-scope.md`
3. `docs/system-architecture.md`
4. `docs/style-bible.md`
5. `tasks/week1-plan.md`

