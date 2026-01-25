这里的大多数模型均以 FastAPI 服务的形式提供。你可以在 `config/lab.toml` 的 [package] 部分配置具体启用哪些内容，比如 FunASR、Whisper、GPTSoVITS 等，然后具体根据需求安装模型。

如果你有安装 just, 那么你可以更快速地利用我给你提供的 justfile 来安装所需模型。

或者你跟我一样很懒，你可以选择把所有模型都安装了。那么运行它：

```shell
just install-model
```
它同样可以用来检查模型是否安装完成。

## FunASR


运行以下命令安装 FunASR 模型。

```shell
just install-funasr-model
```

它包含以下内容:

```shell
$ ls models/
download.md
punc_ct-transformer_zh-cn-common-vocab272727-pytorch/
speech_fsmn_vad_zh-cn-16k-common-pytorch/
speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch/
```

### 标点恢复:

[punc_ct-transformer_zh-cn-common-vocab272727-pytorch](https://modelscope.cn/models/iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch)

或者:<br>

```shell
uv lock
uv sync
uv run modelscope download --model iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch --local_dir ./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
```

### 语音活动检测:

[speech_fsmn_vad_zh-cn-16k-common-pytorch](https://modelscope.cn/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch/files)

```shell
uv lock
uv sync
uv run modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir ./models/speech_fsmn_vad_zh-cn-16k-common-pytorch
```

### ASR模型:

[speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch](https://modelscope.cn/models/iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch)

```shell
uv lock
uv sync
uv run modelscope download --model iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch --local_dir ./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
```

## Whisper

运行以下命令安装 Whisper 模型。

```shell
just install-whisper
```

它包含以下内容:

```shell
$ ls models/
download.md
whisper/
```

或者你可以直接运行以下命令来安装 Whisper:

```shell
uv lock
uv sync
uv run scripts/download.py --url https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt --filename tiny.pt --output-dir ./models/whisper
# large-v3-turbo.pt
uv run scripts/download.py --url https://www.modelscope.cn/models/iic/Whisper-large-v3-turbo/resolve/master/large-v3-turbo.pt --filename large-v3-turbo.pt --output-dir ./models/whisper
```

## GPTSoVITS

它包含两部分，分别是 bert_model 和 gsv_model。前者是运行的前置条件，后者则是自定义音色模型。

### BERT 模型

```shell
just install-bert-model
```

它包含以下内容:

```shell
$ ls models/
download.md
chinese-hubert-base
chinese-roberta-wwm-ext-large
```

或者你可以这样安装:

```shell
uv run modelscope download --model pengzhendong/chinese-hubert-base --local_dir ./models/chinese-hubert-base pytorch_model.bin
uv run modelscope download --model dienstag/chinese-roberta-wwm-ext-large --local_dir ./models/chinese-roberta-wwm-ext-large  \
pytorch_model.bin added_tokens.json config.json configuration.json README.md special_tokens_map.json tokenizer_config.json tokenizer.json
```

### GPTSoVITS 音色模型

```shell
just install-gsv-model
```

它包含以下内容:

```shell
$ ls models/gptsovits/
elaina
```

或者你可以这样安装:

```shell
uv run modelscope download --model xnnehang/elaina-gsv-v2 --local_dir ./models/gptsovits/elaina
```

## Embedding - Memory 试验

本仓库正在实验性支持长期记忆。如果你想尝试，可以将 `config/lab.toml` 中的 `enable_longterm_memory` 设为 `true`。

然后安装 Embedding 模型:

```shell
just install-embedding-model
```

或者你可以直接运行以下命令来安装 Embedding 模型:

```shell
uv lock
uv sync
uv run modelscope download --model iic/nlp_gte_sentence-embedding_chinese-base --local_dir ./models/nlp_gte_sentence-embedding_chinese-base
```