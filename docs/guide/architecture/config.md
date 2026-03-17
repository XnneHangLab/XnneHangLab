# 配置架构

XnneHangLab 的配置以 `config/lab.toml` 为中心，`pydantic` 模型负责校验、补默认值和写回。

## 入口模型

主入口是 `XnneHangLabSettings`，大致结构如下：

```python
class XnneHangLabSettings(BaseModel):
    conf_version: str
    asr: ASRSettings
    webui: AudioRecognizeSettings
    agent: AgentSettings
    local_embedding: LocalEmbeddingSetting
    package: PackagesSettings
    root: RootAbsDir
    server: ServerSettings
    vtuber: VtuberSettings
    memory_bench: MemoryBenchSettings
```

## Agent 分层

`AgentSettings` 现在只负责聊天、视觉、翻译、profile 和工具调用相关配置：

```python
class AgentSettings(BaseModel):
    chat_model: ChatModelSetting
    vision_model: VisionModelSetting
    enable_tool: bool = True
    prompts: PromptSettings
    llm: LLMSettings
    translate_provider: TranslateProvider = "llm"
    translate: TranslateSettings
    user_lang: Literal["ZH", "EN", "JA"] = "ZH"
    speaker_lang: Literal["ZH", "EN", "JA"] = "EN"
    speaker_model: Literal["gpt_sovits"] = "gpt_sovits"
    faster_first_response: bool = False
    max_vision_concurrency: int = 4
    require_detailed: bool = True
    segment_method: Literal["regex", "pysbd"] = "pysbd"
    interrupt_method: Literal["system", "user"] = "user"
    memory_agent_profile: str = "profiles/elaina.toml"
    memory_chat_profile: str = "profiles/congyin.toml"
```

远程 embedding 配置已经从 `AgentSettings` 中移除。

## LocalEmbeddingSetting

本地 embedding 服务使用独立配置块，方便和 `memory_bench`、`/v1/embeddings` 共用：

```python
class LocalEmbeddingSetting(BaseModel):
    model_path: str = "./models/bge-m3-q8_0.gguf"
    pooling_type: Literal["mean", "cls", "last"] = "mean"
    n_gpu_layers: int = 0
```

## Package 开关

`PackagesSettings` 决定哪些服务被挂载和预加载。与本次 embedding 相关的关键字段：

- `local_embedding`
- `memory_bench`
- `llm_translate`

其中 `memory_bench` 现在依赖 `local_embedding`。

## 加载流程

配置加载流程在 `src/lab/config_manager/config.py`：

1. 查找 `config/<name>.toml`
2. 不存在则创建默认文件
3. 使用 `pydantic` 校验
4. 将补全后的结构写回磁盘

这样可以保证配置升级后旧文件会被自动补齐，但不会再保留已经移除的旧字段，比如 `[agent.embedding]`。
