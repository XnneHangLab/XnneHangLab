## 配置

因为我的项目是由一个个 submodule 来构成的。

而它们由几乎有自己的一个配置文件，当它们混合在一起时也相当让人眼花缭乱。

> 提醒一下自己修复一下 as_pacakage 的命名。不能简单用通用的 `settings.toml`, 存在覆盖风险。<br>


所有配置文件均位于 `config/` 下。

其中， `.toml` 文件均是我自己的， `yaml` 和 `json` 文件则不是我的。

## toml

### lab.toml `[funasr]` and `[webui]`

你在运行 just start 后就可以在 UI 的设置中看到它们。这里一般在 UI 中更改。或者你要使用 cli 时可以了解部分。

具体你可以参见 [cli.md](./cli.md)

### lab.toml `[root]`

运行 `uv run get_root` 时生成的记录项目根目录绝对路径的配置文件,无需手动填写，运行时自动生成。

### lab.toml `[package]`

如果你只想允许本项目的部分功能，那么可以考虑调整它。并且跟随调整 pyproject.toml 中的:

```shell
default-groups = ["dev","yutto-uiya","bert-vits","database","vtuber"] 
```

可以起到项目瘦身的效果。当然目前的方案还是有局限性，如果你存在更好的管理方案欢迎提出。

**to_do_list**
- 描述：运行时是否包含待办事项，为 false 则 WebUI 中不再有`代办事项`页面
- 默认值：true
- 特性：仅影响 WebUI

**yutto_uiya** 
- 描述: 运行时是否包含 `b 站视频下载`模块
- 默认值: true
- 特性：仅影响 WebUI

**bert_vits**
- 描述: 运行时是否包含 `bert-vits` 模块, 以及 fastapi 的 lifespan 是否加载 BERT-VITS 模型。
- 默认值: true
- 特性：影响 WebUI 和 fastapi 和 vtuber 功能

**gpt_sovits**
- 描述: 运行时是否包含 `gpt-sovits` 模块, 以及 fastapi 的 lifespan 是否加载 GPT-SoVITS 模型。
- 默认值: true
- 特性：影响 fastapi 和 vtuber 功能

如果你希望使用 Vtuber 功能则需要至少开启 `bert-vits` 或者 `gpt-sovits`。

### lab.toml `[agent]`

均用于 VtuberLab, 如果你不需要该功能那么可以不管这些配置。

**llm_provider**

- 描述: 调用 llm api 时需要的 provider, 与 agent.llm.llm_provider 保持一致。
- 默认值: "lingyi"
- 可选: ["openai", "lingyi", "gemini"]

**enable_mcp**
- 描述: 是否启用 MCP 功能
- 默认值: True
- 注意点: 不是所有模型都支持 function call，比如零一万物的大部分模型都不支持, 所以它无法使用 MCP 功能。

**speaker_lang**
- 描述: TTS 模型生成的目标语言
- 默认值: "EN"
- 可选: ["ZH", "JA", "EN"]
- 注意点： bert_vits 目前只推理中文。

**user_lang**
- 描述: 用户使用的主要语言，决定你看到的模型回复的语言。
- 默认值: "ZH"
- 可选: ["ZH", "JA", "EN"]

**character_name**
- 描述: 角色 system_prompt 所在的位置，对应路径 `./prompt/characters/{character_name}.txt`
- 默认值: "elaina"
- 可选: ["elaina", "paimeng", "neko"] # 你也可以自己替换或者新增提示词。

**speaker_model**
- 描述: 使用的 TTS 模型名称
- 默认值: "gpt_sovits"
- 可选: ["bert_vits", "gpt_sovits"]
- 注意点:
  - bert_vits 的推理设备需要更改 `config/bert_vits.yaml` 中的 `device` 字段，可以全部替换。
  - gpt_sovits 配置位于 `config/gsv_config.yaml` 自动加载显卡如果可用。

**faster_first_response** 

- 描述: 是否生成第一句话的","时就开始异步生成 tts 而不是等待完整句子生成后再开始 tts
- 默认值:false

**deeplx_api_key**
- 描述: deeplx 翻译的 api key
- 默认值: "peach"

**enable_longterm_memory**
- 描述: 是否启用长期记忆功能
- 默认值: true

这两个我不建议你更改。

**segment_method**
**interrupt_method**

#### lab.toml `[agent.llm.*]`

llm 相关配置。你需要至少填写一个。

**llm_api_key**
- 描述: 调用 llm api 时需要的 api key
- 默认值: "peach"

**llm_base_url**
- 描述: 调用 llm api 时需要的 base url
- 默认值: "https://api.lingyiwanwu.com/v1"

**llm_model**
- 描述: 调用 llm api 时需要的模型名称
- 默认值: "yi-lightning"


### lab.toml `[agent.memory]`
**embedding_model_path**
- 描述: 嵌入模型路径(目前仅支持这个模型，而这个模型仅支持中文 =-=，后续得加个英文的或者通用的。)
- 默认值: "./models/nlp_gte_sentence-embedding_chinese-base"
**books_thresholds**
- 描述: 世界书搜索阈值，低于这个阈值的世界书将被过滤掉。专业点叫知识库
- 默认值: 0.5
**mem_thresholds**
- 描述: 核心记忆搜索阈值，低于这个阈值的记忆将被过滤掉。
- 默认值: 0.38
**scan_depth**
- 描述: 扫描深度，扫描记忆的深度。
- 默认值: 4

还有几个暂时没用到

### lab.toml `[mcp.*]`

仅在 `agent.enable_mcp=True` 时工作:

一般不需要手动配置，开发者使用。

**transport**
- 描述: MCP 服务器的 transport 类型
- 默认值: "http"
- 可选: ["http"]

**host**
- 描述: MCP 服务器的 host
- 默认值: "127.0.0.1"

**port**
- 描述: MCP 服务器的 port
- 默认值: 4200

**path**
- 描述: MCP 服务器的 path
- 默认值: "/"

**log_level**
- 描述: MCP 服务器的 log_level
- 默认值: "info"



### `yutto.toml` / `todo.toml` / `uiya.toml`

无需修改和注意的文件, 和 package 对应。均在 WebUI 中使用。

## yaml

### `vtuber.yaml`:

Open-LLM-Vtuber 的配置文件。其中大部分已经用不到，而用得到的部分一般也不需要人来改。

`live2d_model_name` ：配置 live2d 模型。可选项：[`shizuku-local`,`mao_pro`, `elaina-local`]

### `bert_vits.yaml`

Bert-VITS 推理时的配置。

你只需要关心这几行:

dataset_path: "models/BERT-VITS2.3/xishi"  | speaker 路径配置。

device: "cpu" / "cuda" | bert-vits 推理使用的设备, 如果你希望使用 cpu 或者 cuda, 把每处都替换了即可。

model: "models/G_0.pth"  | 模型路径，只需要更改 G_XX 即可，模型具体路径由 dataset_path 也就是 speaker 路径决定。


## json

### `gsv_config.json`

```json
{
  "device": "auto",
  "is_half": "auto",

  "models_path": "models/gptsovits",
  "cnhubert_base_path": "bert/chinese-hubert-base",
  "bert_base_path": "bert/chinese-roberta-wwm-ext-large",
  "save_prompt_cache": true,
  "prompt_cache_dir": "cache/prompt_cache"
}
```

用来配置模型路径用的。一般不必更改, 只需要确认防止的位置即可。