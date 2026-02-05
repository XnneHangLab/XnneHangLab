# AI 维护指南：memory_agent

这份文档用于“喂给大模型”以快速理解模块设计与修改边界。

## 入口与目录

- 入口类：`lab/agent/agents/memory_agent/agent.py::MemoryAgent`
- 目录：`lab/agent/agents/memory_agent/`

## 必须遵守的不变量（强约束）

1. **history/memory 永远不存 base64**
   - 发送给 chat 的 message 可以带图片，但写入 `MemoryStore` 的必须是纯文本 prompt。

2. **最终回答永远由 chat_model 输出**
   - vision_model 只用于生成 summaries（预处理），不能替代 chat 的最终回答。

3. **tool 图与 upload 图语义隔离**
   - tool 回调图默认只取一张（label=tool1），不要混入 upload 的 p1/p2/... 标签里。

4. **require_detailed 的定义**
   - require_detailed=False：一次多图（1 次 vision 调用）生成 upload summaries（当需要 summaries 时）。
   - require_detailed=True：逐图（N 次，可并发）生成 upload summaries。

5. **标签对齐**
   - upload 图片顺序必须与 p1/p2/... summaries 顺序一致。
   - 多图喂给 chat 时，每张图前插入 `[pN]` 文本标签。

## 决策表（最重要）

| chat_supports_vision | require_detailed | 是否需要 vision summaries | chat 输入是否带图片 |
|---|---|---|---|
| False | False | 需要（一次多图） | 不带 |
| False | True  | 需要（逐图并发） | 不带 |
| True  | False | 不需要 | 带 |
| True  | True  | 需要（逐图并发） | 带（并且 summaries 一并喂） |

enable_tool=True 时，额外：
- Prompt 中包含 tool trace JSON
- 若有 tool 图：可生成 tool summary（单张）

## 常见坑（反例）

- ❌ 把 tool 图混进 upload 的 p1/p2：用户会误以为“我只上传了三张，为何出现四个 p?”
- ❌ 逐图并发失败时 silent skip：下游对齐丢失，模型可能脑补缺失项。
- ❌ history 存 base64：会导致存储膨胀与安全风险。

## 建议的错误处理策略

- 逐图并发：失败返回占位，例如：`out["p2"] = "[ERROR] p2 摘要失败: RateLimitError"`
- 解析失败：返回 `{"p_all": raw}` 或 `{"p_all": "..."} ` 保底

## 扩展建议（怎么改最安全）

- 新增功能优先落在子模块：
  - Message 解析/构造 -> `message_factory.py`
  - Prompt 拼装 -> `prompt_builder.py`
  - Vision 逻辑 -> `vision_summarizer.py`
  - Tool 逻辑 -> `tool_runner.py`
  - Memory/History -> `memory_store.py`
- `agent.py` 只改“决策树编排”，不要塞入大量字符串拼接/解析细节。
