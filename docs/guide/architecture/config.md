# 配置模块

`src/lab/config_manager/` 负责 **TOML 配置加载、Pydantic 校验、默认值补全、自动写回**。

它的定位很朴素：让 `lab.toml` 永远是一个可直接读取、结构完整、类型可靠的配置对象，而不是一堆随手拼出来的字典。

---

## 核心设计

### Pydantic 驱动

所有配置都由 **Pydantic BaseModel** 管理，这带来三件事：

- 类型安全：字段类型自动校验
- 默认值集中：默认配置直接写在模型里
- 序列化稳定：`model_dump()` 后可以直接回写 TOML

加载入口很简单：

```python
from lab.config_manager import load_settings_file, XnneHangLabSettings

settings = load_settings_file("lab.toml", XnneHangLabSettings)
```

---

### 加载流程

`load_settings_file()` 的工作顺序是固定的：

1. 搜索配置文件位置
2. 用 `tomllib` 读取 TOML
3. 交给 Pydantic 做校验和默认值补全
4. 用 `tomli_w` 写回完整配置

```python
def load_settings_file(setting_name: str, setting: type[XnneHangLabSettings]) -> XnneHangLabSettings:
    settings_file = search_for_settings_file(setting_name=setting_name)
    if settings_file is None:
        config_dir = Path("config")
        if not config_dir.exists():
            config_dir.mkdir()
        settings_file = config_dir / setting_name
        settings_file.touch()

    with settings_file.open("r", encoding="utf-8") as f:
        settings_raw = tomllib.loads(f.read())

    validated_settings = setting.model_validate(settings_raw)
    write_settings_file(settings_name=setting_name, settings=validated_settings)
    return validated_settings
```

这么设计的原因，是让“缺字段”变成可恢复状态，而不是把运行期异常甩给用户。

---

## 主配置类

`XnneHangLabSettings` 是整个项目的配置入口。当前结构如下：

```python
class XnneHangLabSettings(BaseModel):
    conf_version: str = "v1.5.1"
    asr: ASRSettings
    webui: AudioRecognizeSettings
    agent: AgentSettings
    package: PackagesSettings
    root: RootAbsDir
    server: ServerSettings
    vtuber: VtuberSettings
    memory_bench: MemoryBenchSettings
```

这里的重点不是“字段多”，而是每个子模块都拥有自己的独立模型。这样 UI、服务端、Agent 初始化都能按模块读取，不需要到处手写键名。

---

## 目录结构

```text
config_manager/
├── __init__.py           # 导出 XnneHangLabSettings 和 load_settings_file
├── config.py             # 主配置类 + 加载/写回逻辑
├── agent.py              # AgentSettings 及其子模型
├── asr.py                # ASRSettings / FunASRSettings / WhisperSettings
├── server.py             # ServerSettings
├── vtuber.py             # VtuberSettings / CharacterSettings / TTSPreprocessorConfig
├── package.py            # PackagesSettings
├── abs_root.py           # RootAbsDir
├── audio_recognize.py    # AudioRecognizeSettings
├── memory_bench.py       # MemoryBenchSettings
└── webui_i18n_model.py   # WebUI i18n 基类
```

---

## Agent 配置分层

`AgentSettings` 现在已经不是一个平铺的大表，而是拆成了几组明确的子模型：

- `chat_model`：聊天模型选择
- `vision_model`：视觉模型选择
- `embedding`：向量模型
- `prompts`：Agent 侧提示词路径
- `llm`：不同 provider 的连接配置

```python
class AgentSettings(BaseModel):
    chat_model: ChatModelSetting
    vision_model: VisionModelSetting
    embedding: EmbeddingModelSetting
    enable_tool: bool = True
    prompts: PromptSettings
    llm: LLMSettings
    deeplx_api_key: str = ""
    user_lang: Literal["ZH", "EN", "JA"] = "ZH"
    speaker_lang: Literal["ZH", "EN", "JA"] = "EN"
    speaker_model: Literal["gpt_sovits"] = "gpt_sovits"
    faster_first_response: bool = False
    max_vision_concurrency: int = 4
    require_detailed: bool = True
    segment_method: Literal["regex", "pysbd"] = "pysbd"
    interrupt_method: Literal["system", "user"] = "user"
    memory_agent_profile: str = "profiles/vtuber.toml"
    memory_chat_profile: str = "profiles/congyin.toml"
```

这种拆法的好处是：配置结构和运行时职责是一一对应的，后面接 Profile、Plugin、ToolManager 也更自然。

---

## Package 开关

`PackagesSettings` 控制哪些功能模块会参与启动：

```toml
[package]
funasr = false
whisper = false
gpt_sovits = true
qwen_tts = false
memory_bench = false
to_do_list = true
yutto_uiya = true
```

这层设计不是为了做“大而全”的配置中心，而是为了把运行依赖前移到启动阶段。不开的模块，路由和相关服务就不要硬加载。

---

## 配置文件位置

默认搜索顺序：

1. `{当前目录}/config/lab.toml`
2. `{XDG_CONFIG_HOME}/lab.toml` 或 Windows 的 `~/AppData/lab.toml`

如果都不存在，`load_settings_file()` 会在 `config/` 下创建默认配置。

---

## 与其他模块的关系

- `service_context.py` 会读取配置并初始化 Agent 与服务上下文
- `server.py` 会根据 `[package]` 开关决定加载哪些路由
- `AgentFactory` 会读取 `[agent]`，再继续进入 Profile / Plugin / ToolManager 流程
- `webui_i18n_model.py` 为 WebUI 配置项提供统一的枚举映射能力
