# ⚙️ settings.md — lab.toml 配置说明

`lab.toml` 是 **XnneHangLab** 的主配置文件，后端（ASR / TTS / Translate / Chat）、WebUI、Agent、MCP、包启用开关等都会从这里读取。

> ✅ 这份文档假设你的 `lab.toml` 位于 `./config/lab.toml`（推荐）。
>
> 💡 配置加载规则：程序会优先在项目 `config/` 下找配置；找不到会尝试从系统配置目录读取；再找不到会初始化默认配置并写回（保证字段齐全）。

---

## 🌳 配置结构总览（tree view）

```text
lab.toml
├─ [root]                         # 项目根目录（主要给 Streamlit 找 packages 用）
│  └─ root_dir
│
├─ [package]                      # 模块开关（决定是否启用/显示某些包）
│  ├─ funasr
│  ├─ whisper
│  ├─ to_do_list
│  ├─ yutto_uiya
│  └─ gpt_sovits
│
├─ [asr]                          # ASR 总配置（FunASR / Whisper）
│  ├─ FFMPEG_PATH
│  ├─ device
│  ├─ custom_output_dir
│  ├─ cache_dir
│  ├─ output_dir
│  ├─ asr_model_provider
│  ├─ cut / cut_line
│  ├─ combine / combine_line
│  ├─ max_sentence_length
│  ├─ [asr.funasr]                # FunASR 子配置
│  │  ├─ batch_size_s
│  │  ├─ punctuation_list
│  │  ├─ hot_words_path
│  │  ├─ base_model
│  │  ├─ vad_model
│  │  ├─ punc_model
│  │  ├─ sense_voice_model
│  │  └─ need_punc
│  └─ [asr.whisper]               # Whisper 子配置
│     ├─ whisper_models_base_dir
│     └─ whisper_model_size
│
├─ [webui]                        # Streamlit WebUI 的简单 UI 偏好
│  ├─ guide
│  └─ subtitle_speed
│
├─ [agent]                        # LLM Agent（对话 / 翻译 / 记忆 / 语音等）
│  ├─ llm_provider
│  ├─ enable_mcp
│  ├─ character_name
│  ├─ deeplx_api_key
│  ├─ user_lang
│  ├─ speaker_lang
│  ├─ enable_longterm_memory
│  ├─ speaker_model
│  ├─ faster_first_response
│  ├─ segment_method
│  ├─ interrupt_method
│  ├─ [agent.llm]                 # 不同 LLM 供应商的参数集合
│  │  ├─ [agent.llm.openai]
│  │  ├─ [agent.llm.lingyi]
│  │  ├─ [agent.llm.gemini]
│  │  ├─ [agent.llm.oaipro]
│  │  └─ [agent.llm.cerebras]
│  └─ [agent.memory]              # 长期记忆 / 世界书配置
│     ├─ embedding_model_path
│     ├─ books_thresholds
│     ├─ mem_thresholds
│     ├─ scan_depth
│     ├─ enable_check_memorys
│     ├─ enable_core_memmorys
│     └─ lore_books
│
└─ [mcp]                          # MCP Server 连接配置（HTTP）
   ├─ [mcp.timeemi]
   │  ├─ transport
   │  ├─ host
   │  ├─ port
   │  ├─ path
   │  └─ log_level
   └─ [mcp.vision]
      ├─ transport
      ├─ host
      ├─ port
      ├─ path
      └─ log_level
```

---

## 🧭 配置文件在哪里？（加载与写回规则）

### 🔎 搜索顺序（简化版）
1. `./config/<name>.toml`（推荐：把 `lab.toml` 放在项目 `config/` 下）
2. 系统配置目录（Windows: `~/AppData`；Linux: `~/.config`；或环境变量 `XDG_CONFIG_HOME`）
3. 都没有 → 自动创建默认配置并写入 `./config/<name>.toml`

### ✍️ 自动写回（为什么我改了一点点就多了一堆字段？）
配置会经过校验与补全：  
- 缺少字段 → 用默认值补齐  
- 补齐后会 **立即写回**，保证你的 `lab.toml` 永远是完整的结构（方便你复制/改配置）。

---

## 🧩 [root] 项目根目录

### root_dir
- **作用**：给 Streamlit WebUI 使用的“项目根目录绝对路径”。
- **为什么需要它**：Streamlit 启动后工作目录可能变成 `.`，导致找不到 `packages/` 等目录；因此需要把真实根目录写进配置里，供 UI 在任何位置都能定位资源。

示例：

```toml
[root]
root_dir = "D:\\tmp\\XnneHangLab"
```

---

## 📦 [package] 模块开关

这些布尔值决定某些模块/包是否启用（例如某些 UI 页面、后端挂载项、依赖是否需要等）。

| 配置项 | 默认 | 说明 |
|---|---:|---|
| funasr | true | 是否包含 FunASR 相关能力 |
| whisper | true/false | 是否包含 Whisper 相关能力 |
| to_do_list | true | 是否包含 to-do-list 模块 |
| yutto_uiya | true | 是否包含 yutto-uiya（b站下载相关 UI/能力） |
| gpt_sovits | true | 是否包含 GPT-SoVITS 能力 |

示例：

```toml
[package]
funasr = true
whisper = false
to_do_list = true
yutto_uiya = true
gpt_sovits = true
```

---

## 🎙️ [asr] 语音识别（ASR）总配置

`[asr]` 是 ASR 的入口，`asr_model_provider` 决定实际使用 **FunASR** 或 **Whisper**。

### 关键字段

#### FFMPEG_PATH
- **作用**：指定 ffmpeg 可执行文件路径。
- **常见值**：
  - `"ffmpeg"`：走系统 PATH（推荐）
  - `"C:\\path\\to\\ffmpeg.exe"`：Windows 指向具体 exe

#### device
- **作用**：选择推理设备。
- 可选值：`"cpu"` / `"cuda"`

> 💡 WebUI 中通常会把这类字段做成下拉框（有 i18n 映射）。

#### cache_dir / output_dir
- `cache_dir`：中间缓存（下载、临时文件、切分片段等）
- `output_dir`：输出目录（字幕、导出文件等）

#### asr_model_provider
- **作用**：选择 ASR 提供者。
- 可选值：`"funasr"` / `"whisper"`

#### cut / cut_line（可选）
- `cut = true/false`：是否启用“按间隔切分”
- `cut_line`：切分间隔（毫秒）

#### combine / combine_line（可选）
- `combine = true/false`：是否启用“按间隔合并”
- `combine_line`：合并间隔（毫秒）

#### max_sentence_length
- **作用**：限制最大单句长度（用于字幕行/句子拆分策略）。
- 建议保持默认，除非你明确想要更短/更长的字幕行。

---

### 🧠 [asr.funasr] FunASR 子配置

| 配置项 | 作用 |
|---|---|
| batch_size_s | 批处理大小（单位是秒/片段时长的概念），用于尽量吃满 GPU/CPU |
| punctuation_list | 标点列表，用于分句/后处理 |
| hot_words_path | 热词文件路径（提高特定词识别率） |
| base_model | base 模型路径 |
| vad_model | VAD（语音活动检测）模型路径 |
| punc_model | 标点恢复模型路径 |
| sense_voice_model | SenseVoice 模型路径 |
| need_punc | 是否启用标点恢复（false 表示不额外跑 punc） |

示例：

```toml
[asr.funasr]
batch_size_s = 300
punctuation_list = "，。；、？！,.;?!"
hot_words_path = "./hot_words.txt"
base_model = "./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
vad_model = "./models/speech_fsmn_vad_zh-cn-16k-common-pytorch"
punc_model = "./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
sense_voice_model = "./models/SenseVoiceSmall"
need_punc = false
```

---

### 🌀 [asr.whisper] Whisper 子配置

| 配置项 | 作用 |
|---|---|
| whisper_models_base_dir | Whisper 模型目录 |
| whisper_model_size | 模型规格（目前支持 `tiny` / `turbo`） |

示例：

```toml
[asr.whisper]
whisper_models_base_dir = "./models/whisper/"
whisper_model_size = "turbo"
```

---

## 🖥️ [webui] Streamlit WebUI 偏好

这是给 Streamlit 页面的一些简单偏好设置（偏 UI 体验类）。

### guide
- 可选：`open` / `close`
- **作用**：是否显示指引（新手提示/步骤说明）

### subtitle_speed
- 可选：`slow` / `normal` / `fast`
- **作用**：字幕速度预设（用于“字幕速度调节/演示”等 UI）

示例：

```toml
[webui]
guide = "open"
subtitle_speed = "normal"
```

---

## 🧙‍♀️ [agent] LLM Agent（对话 / 翻译 / 记忆 / 语音）

Agent 主要负责：
- 选择并调用 LLM（不同 provider）
- 角色提示词（character）
- 跨语言对话时的翻译（DeepLX）
- 长期记忆（RAG + 日记/核心记忆/世界书）
- MCP 工具连接（可选）
- 文本分句（用于更自然的 TTS/逐句处理）

### llm_provider
选择默认使用哪家 LLM：

可选：`openai` / `lingyi` / `gemini` / `oaipro` / `cerebras`

> ⚠️ 注意：你仍然需要在对应的 `[agent.llm.<provider>]` 里填好 `llm_api_key`（若该服务需要）。

### enable_mcp
- `true/false`
- **作用**：是否启用 MCP 工具连接（对接 `mcp.*` 配置）

### character_name
- **作用**：选择角色提示词文件名
- 例如：`elaina` → 对应 `./prompts/characters/elaina.txt`

### deeplx_api_key
- **作用**：用于跨语言对话时把 LLM 回复翻译成 speaker 语言，再合成语音。
- 通常在 `user_lang != speaker_lang` 时才会用到。如果没有它就只能同语言对话。

> 它是 Linux.do 社区里始皇提供给每个用户的 key，可以免费使用 deeplx(beta) 翻译服务。 <br>
> 具体可以参考这里 [配置始皇DeepLX的沉浸式翻译](https://linux.do/t/topic/1431373)。

### user_lang / speaker_lang
- 可选：`ZH` / `EN` / `JA`
- `user_lang`：用户输入语言，也会影响 LLM 回复语言策略  
- `speaker_lang`：语音合成端输出语言（TTS 目标语言）

### enable_longterm_memory
- `true/false`
- **作用**：是否启用长期记忆模块（具体策略见 `[agent.memory]`）

### speaker_model
- 当前可选：`gpt_sovits`
- **作用**：选择用于语音合成的模型类型（后续可扩展更多模型）

### faster_first_response
- `true/false`
- **作用**：偏“更快首句/首包”的响应策略开关（用于优化体感响应速度）

### segment_method
- 可选：`regex` / `pysbd`
- **作用**：文本分句方法
  - `regex`：用正则/标点切分（简单直接）
  - `pysbd`：用句子边界检测（更像自然语言分句）

### interrupt_method
- 可选：`system` / `user`
- **作用**：把“打断信号”写入 chat history 的方式：
  - `system`：用系统提示写入
  - `user`：用用户输入写入

示例：

```toml
[agent]
llm_provider = "openai"
enable_mcp = true
character_name = "elaina"
user_lang = "ZH"
speaker_lang = "EN"
enable_longterm_memory = true
speaker_model = "gpt_sovits"
segment_method = "pysbd"
interrupt_method = "user"
```

---

### 🤖 [agent.llm] LLM 供应商配置（OpenAI-compatible）

每个 provider 结构一致：

- `llm_api_key`
- `llm_base_url`
- `llm_model_name`

你只需要给你选中的 `llm_provider` 填对 key / base_url / model 即可；其他 provider 可以留空当备用。

示例（OpenAI）：

```toml
[agent.llm.openai]
llm_api_key = "sk-***"
llm_base_url = "https://api.openai.com/v1"
llm_model_name = "gpt-4o"
```

示例（Cerebras）：

```toml
[agent.llm.cerebras]
llm_api_key = "cb-***"
llm_base_url = "https://api.cerebras.ai/v1"
llm_model_name = "llama-3.3-70b"
```

---

### 🧠 [agent.memory] 长期记忆 / 世界书配置

这部分借鉴了“暴力 RAG + 时序日记”的思路，提供：
- 世界书（知识库）
- 日记（按时间记录）
- 核心记忆（关于用户的重要长期信息）

#### embedding_model_path
- **作用**：嵌入模型路径（用于语义检索）
- 默认：`./models/nlp_gte_sentence-embedding_chinese-base`（当前主要支持中文）

#### books_thresholds
- **作用**：知识库检索阈值（相似度过滤）
- **经验**：阈值越高 → 命中更准但更少；阈值越低 → 命中更多但可能夹杂噪声

#### mem_thresholds
- **作用**：日记内容检索阈值（相似度过滤）

#### scan_depth
- **作用**：检索深度（返回候选数量上限）
- 注意：仍会被阈值过滤，最终返回数量可能小于 `scan_depth`

#### enable_check_memorys
- **作用**：启用“日记检索加强”
- 行为：对检索到的内容做进一步提取/过滤，减少无关信息混入上下文

#### enable_core_memmorys
- **作用**：启用核心记忆
- 核心记忆用于存储“用户重要信息”（例如偏好/习惯/关键信息等），是语义匹配（模糊检索），不按时间筛选，但每条记忆仍带记录时间。

#### lore_books
- **作用**：启用世界书（知识库）
- 用于补充人物、物品、事件设定，强化角色扮演或知识补充

示例：

```toml
[agent.memory]
embedding_model_path = "./models/nlp_gte_sentence-embedding_chinese-base"
books_thresholds = 0.5
mem_thresholds = 0.38
scan_depth = 4
enable_check_memorys = true
enable_core_memmorys = true
lore_books = true
```

---

## 🔌 [mcp] MCP Server 连接配置（HTTP）

本项目的 MCP 连接方式使用 **HTTP（streamable-http）**，不使用 stdio。

每个 server 都有相同字段：

- `transport`：目前固定 `http`
- `host`：默认 `127.0.0.1`
- `port`：端口
- `path`：默认 `/`
- `log_level`：默认 `debug`

示例：

```toml
[mcp.timeemi]
transport = "http"
host = "127.0.0.1"
port = 4200
path = "/"
log_level = "debug"

[mcp.vision]
transport = "http"
host = "127.0.0.1"
port = 4201
path = "/"
log_level = "debug"
```

> 💡 当 `[agent].enable_mcp = true` 时，Agent 会按这里的地址尝试连接对应 MCP server。
> 这个时候必须先运行 `just mcp-server` 先启动 MCP server，否则 Agent 会报错。

---

## 🧼 最后的小建议

- 🔐 **别把 API Key 提交到 Git**：建议把 `config/lab.toml` 加入 `.gitignore`，或提供 `lab.example.toml` 作为模板。
- 🔁 修改配置后建议重启服务：配置通常在启动时读取，运行中不一定热更新。
- 🧩 模块开关优先：如果某些模块禁用（`[package]`），对应 UI/功能可能不会出现，这是预期行为。
