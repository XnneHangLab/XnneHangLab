# Agent 模块

`src/lab/agent/` — LLM 调用、工具循环、记忆管理。

## 目录结构

```
agent/
├── agent_factory.py          # AgentFactory：根据配置创建 Agent
├── stateless_llm_factory.py  # LLMFactory：创建 OpenAI Compatible LLM 实例
├── stateless_llm/
│   └── openai_compatible_llm.py  # AsyncLLM：异步流式 LLM 调用
├── input_types.py            # 输入类型（BatchInput / ImageData / TextData）
├── output_types.py           # 输出类型（SentenceOutput / AudioOutput / Actions）
├── transformers.py           # 文本后处理管线（断句、表情提取、TTS 过滤）
├── mcp_tool_loop.py          # MCP 工具循环执行器
└── agents/
    ├── agent_interface.py    # AgentInterface：抽象基类
    └── memory_agent/         # MemoryAgent：当前唯一实现
        ├── agent.py          # 编排器（orchestrator）
        ├── memory_store.py   # 内存消息列表 + 历史读写
        ├── message_factory.py # OpenAI Message 构造
        ├── prompt_builder.py  # System Prompt 拼装
        ├── tool_runner.py     # MCP 工具执行 + 回调图提取
        ├── vision_summarizer.py # 图片摘要生成
        └── types.py           # 内部类型
```

## 核心概念

### AgentInterface

所有 Agent 的抽象接口，定义三个核心方法：

- `chat(input_data) → AsyncIterator[BaseOutput]` — 异步流式对话
- `handle_interrupt(heard_response)` — 处理用户打断
- `set_memory_from_history(conf_uid, history_uid)` — 从历史加载记忆

### MemoryAgent

当前唯一的 Agent 实现，职责是**纯编排**——自己不做拼接/解析，全部委托给子组件：

| 组件 | 职责 |
|------|------|
| `PromptBuilder` | 拼装 system prompt（base + vision summaries） |
| `MessageFactory` | 构造 OpenAI 格式消息（支持多图、标签隔离） |
| `MemoryStore` | 维护对话记忆 + 历史持久化 |
| `ToolRunner` | 运行 MCP tool loop，收集 trace 和回调图 |
| `VisionSummarizer` | 对图片生成文本摘要（快模式/细模式） |

### 模式矩阵

MemoryAgent 的行为由配置决定：

- **enable_tool** — 是否先运行 MCP tool loop 再 chat
- **chat_supports_vision** — chat model 是否接受图片输入
- **faster_first_response** — 工具循环完成后是否加速首句响应
- **segment_method** — 断句方式（`pysbd` / 中文标点）
- **interrupt_method** — 中断信号注入方式（`system` / `user`）

### 输入 / 输出类型

**输入：**
- `BatchInput` — 包含文本列表 + 可选图片 / 文件
- `ImageData` — 图片（camera / screen / clipboard / upload）
- `TextData` — 文本（input / clipboard），可带发送者名称

**输出（流式 yield）：**
- `SentenceOutput` — 一句话：display_text + tts_text + actions（表情/图片/音效）
- `AudioOutput` — 一段音频：audio_path + display_text + transcript + actions

## 数据流

一次完整的对话请求经过以下处理管线：

```
📥 BatchInput（用户输入）
    ↓
🔧 [enable_tool?] ToolRunner
    → tool_trace + tool_images
    ↓
👁️ [has_images?] VisionSummarizer
    → vision_summaries
    ↓
📝 PromptBuilder
    → system_prompt (base + summaries)
    ↓
✉️ MessageFactory
    → OpenAI messages (prompt + text + images)
    ↓
🤖 AsyncLLM.chat_completion_stream
    → raw LLM response (streaming)
    ↓
🔄 Transformers 管线
    sentence_divider      # 断句
      → actions_extractor # 提取表情/音效
      → tts_filter        # TTS 文本清理
      → display_processor # 显示文本处理
    ↓
📤 yield SentenceOutput
    (display_text, tts_text, actions)
```

**关键节点：**
- 🔧 工具调用是可选的（`enable_tool=True` 时触发）
- 👁️ 图片摘要根据模型能力决定（chat 不支持 vision 时必须生成）
- 🔄 Transformers 是纯文本后处理，不涉及 LLM 调用
- 📤 输出是流式的，逐句 yield

## 不变量

- **History 不写 base64**：memory_store 只持久化纯文本内容
- **Tool 图与用户图隔离**：tool 回调图默认标签 `tool1`，与用户上传图语义分离
