# Config 模块

`src/lab/config_manager/` — TOML 配置加载与校验。

## 核心设计

### Pydantic 驱动的配置管理

所有配置均以 **Pydantic BaseModel** 管理，提供：
- **类型安全** — 字段类型自动校验
- **默认值** — Field() 定义默认配置
- **序列化** — model_dump() 转为字典，tomli_w 写入 TOML

### 配置加载流程

```python
from lab.config_manager import load_settings_file, XnneHangLabSettings

settings = load_settings_file("lab.toml", XnneHangLabSettings)
```

`load_settings_file()` 会：
1. 搜索配置文件（当前目录 `config/` → XDG_CONFIG_HOME）
2. 使用 `tomllib` 读取 TOML（Python 3.11+ 内置）
3. Pydantic 校验并填充默认值
4. 使用 `tomli_w` 回写（补全缺失字段）

### 主配置类

```python
class XnneHangLabSettings(BaseModel):
    conf_version: str = "v1.1.2"  # 配置版本（见入门文档）
    asr: ASRSettings
    agent: AgentSettings
    mcp: MCPSettings
    package: PackagesSettings
    server: ServerSettings
    vtuber: VtuberSettings
    webui: AudioRecognizeSettings
    root: RootAbsDir
```

## 目录结构

```
config_manager/
├── __init__.py           # 导出 XnneHangLabSettings 和 load_settings_file
├── config.py             # XnneHangLabSettings：主配置类 + 加载/写入逻辑
├── agent.py              # AgentSettings：Agent 配置
├── asr.py                # ASRSettings / FunASRSettings / WhisperSettings
├── server.py             # ServerSettings：服务器配置
├── vtuber.py             # VtuberSettings / CharacterSettings / TTSPreprocessorConfig
├── package.py            # PackagesSettings：功能开关
├── abs_root.py           # RootAbsDir：根目录配置
├── audio_recognize.py    # AudioRecognizeSettings：WebUI 音频识别配置
├── mcp.py                # MCPSettings：MCP 工具配置
└── webui_i18n_model.py   # WebUI 国际化配置
```

## Package 开关（功能模块）

`PackagesSettings` 控制哪些功能模块被加载：

```toml
[package]
funasr = false           # FunASR 语音识别
whisper = false          # Whisper 语音识别
gpt_sovits = true        # GPT-SoVITS TTS
qwen_tts = false         # Qwen-TTS（faster-qwen-tts）
memory_bench = false     # Memory Bench 记忆服务（路由前缀 /memory）
to_do_list = true        # TODO List 功能
yutto_uiya = true        # Yutto-Uiya 功能
```

**路由条件加载：**
- `funasr=true` 或 `whisper=true` → 加载 `/asr/*`
- `gpt_sovits=true` → 加载 `/tts/gptsovits*`
- `qwen_tts=true` → 加载 `/tts/qwen-tts/*`
- `memory_bench=true` → 加载 `/memory/*`

## 配置文件位置

默认搜索顺序：
1. `{当前目录}/config/lab.toml`
2. `{XDG_CONFIG_HOME}/lab.toml`（Linux/macOS: `~/.config/`，Windows: `~/AppData/`）

如果不存在，`load_settings_file()` 会在 `config/` 下创建默认配置。

## 与其他模块的关系

- **所有模块** 通过 `load_settings_file()` 读取配置
- **service_context.py** 使用配置初始化 Agent 和服务
- **server.py** 根据 `package` 开关决定加载哪些路由和模型
- **配置热重载** — 部分模块（如 FunASR）支持 `/asr/reload` 端点重载模型
