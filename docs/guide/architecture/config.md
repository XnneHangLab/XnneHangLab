# Config 模块

`src/lab/config_manager/` — TOML 配置加载与校验。

## 目录结构

```
config_manager/
├── __init__.py           # 导出 XnneHangLabSettings 和 load_settings_file
├── config.py             # XnneHangLabSettings：主配置类
├── agent.py              # AgentSettings：Agent 配置
├── asr.py                # ASRSettings：语音识别配置
├── server.py             # ServerSettings：服务器配置
├── vtuber.py             # CharacterSettings / TTSPreprocessorConfig
├── package.py            # PackageSettings：功能开关
├── abs_root.py           # RootSettings：根目录配置
├── audio_recognize.py    # AudioRecognizeSettings：音频识别配置
├── mcp.py                # MCPSettings：MCP 工具配置
└── webui_i18n_model.py   # WebUI 国际化配置
```

## 核心概念

### XnneHangLabSettings

主配置类，聚合所有子配置：

```python
class XnneHangLabSettings(BaseModel):
    root: RootSettings
    package: PackageSettings
    agent: AgentSettings
    asr: ASRSettings
    mcp: MCPSettings
    # ...
```

### 配置加载

```python
from lab.config_manager import load_settings_file, XnneHangLabSettings

settings = load_settings_file("lab.toml", XnneHangLabSettings)
```

`load_settings_file()` 会：
1. 从 `root_dir` 读取 TOML 文件
2. 使用 Pydantic 校验
3. 返回类型安全的配置对象

### 配置文件位置

默认配置文件：`{root_dir}/lab.toml`

可通过环境变量 `XNNEHANGLAB_ROOT` 覆盖根目录。

## 关键配置项

### Agent 配置

```toml
[agent]
enable_mcp = true
chat_model = { llm_provider = "openai", llm_model_name = "gpt-4" }
tool_model = { llm_provider = "openai", llm_model_name = "gpt-4" }
vision_model = { llm_provider = "openai", llm_model_name = "gpt-4-vision" }
faster_first_response = true
segment_method = "pysbd"
interrupt_method = "user"
```

### MCP 配置

```toml
[[mcp.servers]]
name = "tool"
url = "http://localhost:8001/mcp/sse"

[[mcp.servers]]
name = "vision"
url = "http://localhost:8001/mcp/vision/sse"
```

### Package 开关

```toml
[package]
funasr = true
whisper = false
to_do_list = false
yutto_uiya = false
```

## 与其他模块的关系

- **所有模块** 通过 `load_settings_file()` 读取配置
- **service_context.py** 使用配置初始化 Agent 和服务
- **server.py** 根据配置决定加载哪些路由和模型
