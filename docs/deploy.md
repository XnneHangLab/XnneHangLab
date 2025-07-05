## 本地部署

### 0.前置

> 如果你这三个都已经安装好了，那么可以跳到下一步。 

- [x] ffmpeg
- [x] uv
- [x] just

---

> 如果你是 windows , 可以先安装 [**scoop**](https://scoop.sh/) , 这样可以更方便的安装依赖。<br>
> 只需要打开 powershell 然后运行:<br>
>
> ```shell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
> ```
>
> 之后你就可以在任何终端使用 scoop.<br>

[**ffmpeg**](https://www.ffmpeg.org/), 本项目的依赖项 `yutto` 用到系统的 `ffmpeg`, 目前 `ffmpeg` 需要在全局可以访问, 对于 mac 和 linux 用户可以直接:

```shell
sudo apt install ffmpeg # linux
brew install ffmpeg # mac
scoop install ffmpeg # windows
```

也可以下载 ffmpeg 的可执行文件然后添加到全局设置和 `b站视频下载` 是 ffmpeg 路径设置项中.

[**uv**](https://docs.astral.sh/uv/) 是本项目的包管理工具，它让你免于手动配置和调试环境。你可以从[安装指南](https://docs.astral.sh/uv/getting-started/installation/)找到合适的安装方式～

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh # linux / mac
scoop install uv # windows
# 完整完均需要新开终端
```

[**just**](https://github.com/casey/just) 是一款用 rust 编写的简单易用的命令执行工具，它可以让原本复杂的命令运行变得简单。安装方法请参考[它的文档](https://github.com/casey/just#installation)。该项非必须， Windows 比较难安装 just (当然如果你有 scoop 和 git bash 可以直接 `scoop install just`), 可以跳过。后续使用 bat 脚本替代即可。

```shell
# windows
scoop install git
scoop install just

# linux / mac
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh # rust-tool-chain, 安装新开终端
cargo install just
```

**ps:** windows 用户也可以等待网盘的整合包。整合包双击运行,包含所有环境以及依赖.

### 1. 克隆仓库

```shell
git clone https://github.com/XnneHangLab/XnneHangLab.git --recurse-submodules
cd XnneHangLab
```

你应该保证 `submodules` 都被克隆完全。只要保证 `packages/*/`,`static/`,`examples` 均不为空即可。 

如果某个目录为空，可以后续手动更新比如：

```shell
git submodule update --init --recursive examples
```

### 2. 自动安装依赖并下载必要模型权重文件

如果你有 just:

```shell
just install-model
```

过程可能较久，因为需要先安装 python 环境，然后再下载模型， 模型和环境都不小, 建议可以先构建 cpu 版本进行功能预览，等有性能和批处理需求了再构建 gpu 版本的 torch。

更改 pyproject.toml 的这几行即可：

```toml
# windows 下安装 pytorch-cuda, linux 和 mac 下安装 pytorch-cpu, 你可以根据你的系统和需求任意修改
[tool.uv.sources]
torch = [
  { index = "pytorch-cu118", marker = "sys_platform == 'win32'" }, # sys_platform : 'win32' , 'linux' , 'Darwin'
  { index = "pytorch-cpu", marker = "sys_platform != 'win32'"}
]
torchaudio = [
  { index = "pytorch-cu118", marker = "sys_platform == 'win32'" },
  { index = "pytorch-cpu", marker = "sys_platform != 'win32'"}
]
```

默认 windows 下是 pytorch-cu118 , linux 和 mac 下是 pytorch-cpu, 如果你希望在 windows 下安装 cpu 或者在 linux 下安装 cuda 可以直接对调即可。

你可以通过重复运行来验证模型是否下载完整:

```shell
(xnnehanglab) xnne@xnne-PC:~/code/XnneHangLab$ just install-model
uv lock
Resolved 106 packages in 5ms
uv sync
Resolved 106 packages in 6ms
Audited 100 packages in 0.49ms
# ASR with hotwords
uv run modelscope download --model iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch --local_dir ./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
Downloading Model from https://www.modelscope.cn to directory: /home/xnne/code/XnneHangLab/models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
2025-03-31 20:41:31,448 - modelscope - WARNING - Model revision not specified, use revision: v2.0.4
uv run modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir ./models/speech_fsmn_vad_zh-cn-16k-common-pytorch
...
```
### 3. 准备 bert 预训练模型 (如果你希望使用 VTuber 功能)

```shell
xnnehanglab➜  VtuberLab git:(add-gpt-sovits) ✗ ls bert 
chinese-hubert-base  chinese-roberta-wwm-ext-large  deberta-v2-large-japanese-char-wwm  deberta-v3-large
```

其中 gpt_sovits 仅用到 `chinese-hubert-base  chinese-roberta-wwm-ext-large `

BERT_VITS 几乎全用到了。

你可以选择从 hugging face 上下载。或者一样从我的网盘下载:

```shell
链接: https://pan.baidu.com/s/1BkrkAc7QvrJeYL6MfEizZQ?pwd=fdri 提取码: fdri 
```


### 4. 手动下载 BertVITS2.3 的模型。(如果你希望使用 VTuber 功能)

有几种下载途径：

- 直接从 hugging face 上下官方的底模: https://huggingface.co/OedoSoldier/Bert-VITS2-2.3/tree/main
- 从我的网盘上下: 
```shell
链接: https://pan.baidu.com/s/1ItMmGUAnqlD7FhvqkUnvCQ?pwd=h22x
提取码: h22x 
```

你只需要保证你的模型目录是这样的即可:

```shell
xnnehanglab➜  VtuberLab git:(copy-open-llm-vtuber) ✗ ls models 
BERT-VITS2.3  punc_ct-transformer_zh-cn-common-vocab272727-pytorch  speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
download.md   speech_fsmn_vad_zh-cn-16k-common-pytorch

xnnehanglab➜  BERT-VITS2.3 git:(copy-open-llm-vtuber) ✗ tree
.
└── xishi
    ├── config.json
    ├── configs
    │   └── config.json
    └── models
        ├── D_0.pth
        ├── DUR_0.pth
        ├── G_0.pth
        └── train.log
```

## 5.手动下载 GPTSoVITS 模型(如果你希望使用 VTuber功能)

原作者@[基于GPT-SoVITS的伊蕾娜自恋语音合集（附模型）](https://www.bilibili.com/video/BV1Df421m7bm/?spm_id_from=333.337.search-card.all.click&vd_source=d7601f0fc447d708fff71aa75186ea10)

```shell
链接: https://pan.baidu.com/s/1TlvFGx3bzOdZh2RydVAfpQ?pwd=hbfc 提取码: hbfc 
```

你应该把它这样放置:

```shell
xnnehanglab➜  VtuberLab git:(add-gpt-sovits) ✗ ls models 
BERT-VITS2.3  gptsovits     hub                                                   speech_fsmn_vad_zh-cn-16k-common-pytorch
download.md   gptsovits.7z  punc_ct-transformer_zh-cn-common-vocab272727-pytorch  speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
xnnehanglab➜  VtuberLab git:(add-gpt-sovits) ✗ tree models/gptsovits 
models/gptsovits
└── elaina
    ├── elaina_e10_s490.pth
    ├── elaina-e25.ckpt
    ├── elaina.wav
    └── infer_config.json

1 directory, 4 files
```


## 运行一下看看

启动 streamlit WebUI

```shell
just start
```

启动后端:

```shell
just server
```

如果你只想要使用部分功能，那么请参考 [关于 packages.toml](settings.md#packagetoml) 进行配置。

默认开启所有功能，你需要下载所有模型和依赖。

如果你需要进行对话，记得要先在 `config/agent.toml` 中配置你的使用的 openai 模型与 api key。

配置相关详细参见: [关于 agnet.toml](./settings.md#agenttoml)