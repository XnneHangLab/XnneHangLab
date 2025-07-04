## 配置

因为我的项目是由一个个 submodule 来构成的。

而它们由几乎有自己的一个配置文件，当它们混合在一起时也相当让人眼花缭乱。

> 提醒一下自己修复一下 as_pacakage 的命名。不能简单用通用的 `settings.toml`, 存在覆盖风险。<br>


所有配置文件均位于 `config/` 下。

其中， `.toml` 文件均是我自己的， `yaml` 文件则不是我的。

## toml

### `funasr.toml` / `audio.toml` /  `uiya.toml`

你在运行 just start 后就可以在 UI 的设置中看到它们。这里一般在 UI 中更改。或者你要使用 cli 时可以了解部分。

具体你可以参见 [cli.md](./cli.md)

### root.toml

运行 `uv run get_root` 时生成的记录项目根目录绝对路径的配置文件。

### package.toml

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
- 特性：影响 WebUI 和 fastapi

如果你希望使用 Vtuber 功能则需要至少开启 `bert-vits`。

### `agent.toml`

均用于 VtuberLab, 如果你不需要该功能那么可以不管这些配置。

**openai_base_url**
- 描述: openai base url
- 默认值: "https://api.lingyiwanwu.com/v1"
- 注意点：请写到 `v1/`

**openai_api_key** 
- 描述: openai 对应的 api key
- 默认值: "peach"

**openai_model** 
- 描述: 使用的模型的 model name. 比如 gpt-4o
- 默认值:"yi-lightning"

**faster_first_response** 

- 描述: 是否每生成一句话就开始异步生成 tts 而不是等待所有段落生成后再生成 tts
- 默认值:true

这两个我不建议你更改。

**segment_method**
**interrupt_method**

### `setting.toml` / `todo.toml` / `video.toml`

无需修改和注意的文件。


## yaml

### `vtuber.yaml`:

Open-LLM-Vtuber 的配置文件。其中大部分已经用不到，而用得到的部分一般也不需要人来改。

`live2d_model_name` ：配置 live2d 模型。可选项：[`shizuku-local`,`mao_pro`]

### `bert_vits.yaml`

Bert-VITS 推理时的配置。

你只需要关心这几行:

dataset_path: "models/BERT-VITS2.3/xishi"  | speaker 路径配置。

device: "cpu" / "cuda" | bert-vits 推理使用的设备, 如果你希望使用 cpu 或者 cuda, 把每处都替换了即可。

model: "models/G_0.pth"  | 模型路径，只需要更改 G_XX 即可，模型具体路径由 dataset_path 也就是 speaker 路径决定。
