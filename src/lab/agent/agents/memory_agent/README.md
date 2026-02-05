# memory_agent

这个目录将原本接近 1000 行的 `MemoryAgent` “上帝类”拆分为多个职责清晰的模块，让代码更易读、易测、易维护。

## 入口

- 入口类：`MemoryAgent`（`agent.py`）
- 导出路径：`from lab.agent.agents.memory_agent import MemoryAgent`

## 模式矩阵（行为规格）

维度：

- `enable_tool`：是否先运行 MCP tool loop，再进行最终 chat
- `chat_supports_vision`：chat_model 是否支持图片输入
- `require_detailed`：用于区分“逐图（N 次）”vs“一次多图（1 次）”生成 *upload* summaries（当需要 summaries 时）

关键规则：

1. **最终回答永远由 chat_model 输出**（streaming + TTS pipeline）；vision_model 仅用于摘要预处理。
2. **history/memory 永远不存 base64**，只存最终发送给 chat 的纯文本 prompt。
3. **tool 回调图与 upload 图语义隔离**：tool 默认只取一张（最新/第一张策略），标签为 `tool1`；upload 以 `p1/p2/...` 标记。

## 目录结构与职责

- `agent.py`：编排器（orchestrator）。只保留决策树与组件调用，避免塞入拼接/解析细节。
- `types.py`：dataclass 结构体（ImagePayload、ToolRunResult、VisionSummaryResult）。
- `message_factory.py`：OpenAIMessage 的解析与构造（带标签多图等）。
- `prompt_builder.py`：纯文本 prompt 拼装（base prompt / summaries prompt）。
- `vision_summarizer.py`：vision 摘要服务（缓存、并发、解析）。
- `tool_runner.py`：MCP tool loop 封装（trace + tool 图片抽取）。
- `memory_store.py`：memory + history + interrupt 管理。

## 扩展点

- 如果未来要支持 tool 回调多张图：优先在 `tool_runner.py` 扩展策略，并在 docs 中更新“tool 图默认单张”的规则。
- 如果要支持 http(s) image_url：在 `message_factory.extract_text_and_data_images` 扩展解析逻辑。

相关架构文档：
- `docs/architecture/memory_agent.md`
- `docs/ai/memory_agent.md`
