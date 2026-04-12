# LLM Interface

这个目录用于承载与 LLM 相关的运行时接口层。

当前它的定位是：

- 组织远程强模型与本地模型的协作
- 承载 `seed pack` 与 `resolved pack` 的类型
- 为后续的 provider、prompt、后台生成任务提供固定落点

它不直接负责：

- schema 校验
- 内容装配
- runtime 状态写回

这些仍然分别属于：

- `state_adapter`
- `runtime`
- `enforcement`
- `memory`

后续建议在这个目录中继续增加：

- `client.py`
- `prompts/`
- `jobs.py`
- `narration.py`
- `memory.py`
- `content.py`
