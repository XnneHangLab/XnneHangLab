    # MemoryAgent 架构说明

    本文描述 `MemoryAgent` 的模块分层、数据流与关键决策，面向工程维护与架构理解。

    ## 模块分层

    ```mermaid
    flowchart LR
      A[MemoryAgent(agent.py)
Orchestrator] --> B[ToolRunner
(tool_runner.py)]
      A --> C[VisionSummarizer
(vision_summarizer.py)]
      A --> D[PromptBuilder
(prompt_builder.py)]
      A --> E[MessageFactory
(message_factory.py)]
      A --> F[MemoryStore
(memory_store.py)]
    ```

    - **MemoryAgent（编排器）**：只负责“决策树”与组件调用，避免拼接/解析细节膨胀。
    - **ToolRunner**：运行 MCP tool loop，返回 tool trace JSON + tool 回调图（默认单张 `tool1`）。
    - **VisionSummarizer**：对 tool 图与 upload 图生成 summaries，支持：
      - 快模式（一次多图 1 次调用）
      - 细模式（逐图并发 N 次调用，带并发上限）
    - **PromptBuilder**：纯文本 prompt 拼装（base / summaries）。
    - **MessageFactory**：OpenAIMessage 解析与构造（带标签多图）。
    - **MemoryStore**：memory + history + interrupt（不存 base64）。

    ## 决策树（核心逻辑）

    维度：
    - `enable_tool`
    - `chat_supports_vision`
    - `require_detailed`

    ### 关键规则

    1. **最终回答由 chat_model 输出**（streaming）；vision_model 仅用于摘要预处理。
    2. **history 不存 base64**：即使发送给 chat 的 message 带图片，写入 history 的只存文本 prompt。
    3. **tool 图与 upload 图隔离**：tool 图默认单张，不混入 upload 的 p1/p2 标签。

    ### 行为矩阵

    | chat_supports_vision | require_detailed | 行为 |
    |---|---|---|
    | False | False | vision 一次多图 → 得到 p1/p2... summaries → 纯文本喂给 chat |
    | False | True  | vision 逐图并发 → 得到 p1/p2... summaries → 纯文本喂给 chat |
    | True  | False | 不生成 summaries；图片直接喂给 chat（带标签） |
    | True  | True  | 生成逐图 summaries + 图片一并喂给 chat（图+摘要双保险） |

    `enable_tool=True` 时，先追加 tool loop 的 trace JSON，并可额外对 tool 图生成 tool summary。

    ## 性能与成本

    - 并发（Semaphore + gather）主要降低 **墙钟时间**，不降低 token 成本。
    - `max_vision_concurrency` 是 in-flight vision 请求上限，用于防止限流与拥塞。
    - 快模式（一次多图）在成本与等待时间上更优，但细节/一致性可能不如逐图。

    ## 失败策略（推荐）

    - 逐图并发时：某张失败应返回占位（例如 `[ERROR] p2 摘要失败: ...`），避免 silent drop 导致下游对齐失败。
    - 解析失败：降级为 `p_all`（或 `p_all`）保底，确保链路不中断。

    ## 扩展点

    - tool 多图：在 `ToolRunner` 改为收集 image_refs 列表，并给出 tool1/tool2... summaries。
    - 支持 http(s) 图片：在 `MessageFactory.extract_text_and_data_images` 扩展。
