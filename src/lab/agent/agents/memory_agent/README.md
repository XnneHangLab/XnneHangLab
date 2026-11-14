# memory_agent

`MemoryAgent` 将 `AgentCore` 的流式输出接入断句、TTS 和 Live2D 管线。

- `agent.py`：编排聊天和输出，管理历史写回。
- `types.py`：带标签的 `ImagePayload`。
- `message_factory.py`：解析和构造 OpenAI 消息，包括多图输入。
- `prompt_builder.py` / `user_prompt_block.py`：拼装结构化文本上下文，兼容已保存的历史。
- `memory_store.py`：会话消息、历史和打断管理。

图片直接交给支持视觉的聊天模型；纯文本模型收到图片时得到无法分析图片的提示。工具截图使用 `tool1` 标签，上传图片使用 `p1/p2/...` 标签。历史只保存文本，不保存图片 base64。

按需看屏幕通过 `screen_shot` 将新鲜截图直接交给聊天模型；启用 `[plugins.screen_shot].enable_ocr` 后，可另行调用 `screen_ocr` 读取台词或字幕。OCR 使用独立截图，并返回采集标识和 UTC 时间。普通 `mood_chat` 按心情和时间调度，不消费视觉事件。

详见 [MemoryAgent 架构](../../../../../docs/guide/architecture/memory-agent.md)。

视觉采集、关键帧回顾的设计与上游同步记录见 [screen_shot/DESIGN.md](../../../plugins/screen_shot/DESIGN.md)。
