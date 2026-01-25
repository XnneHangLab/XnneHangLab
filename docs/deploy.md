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

你应该保证 `submodules` 都被克隆完全。只要保证 `packages/*/`,`static/`,`examples`,`frontend` 均不为空即可。 

如果某个目录为空，可以后续手动更新比如：

```shell
git submodule update --init --recursive examples static packages/* frontend
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
(xnnehanglab) PS D:\tmp\XnneHangLab> ls .\models\


    目录: D:\tmp\XnneHangLab\models


Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
d-----         2026/1/25     19:00                chinese-hubert-base
d-----         2026/1/25     19:00                chinese-roberta-wwm-ext-large
d-----         2026/1/25     18:56                gptsovits
d-----         2026/1/25     18:59                nlp_gte_sentence-embedding_chinese-base
d-----         2026/1/25     18:58                punc_ct-transformer_zh-cn-common-vocab272727-pytorch
d-----         2026/1/25     18:59                SenseVoiceSmall
d-----         2026/1/25     18:58                speech_fsmn_vad_zh-cn-16k-common-pytorch
d-----         2026/1/25     18:59                speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
d-----          2026/1/6     16:45                whisper
-a----         2026/1/25     18:58           4130 download.md
```

阅读 download.md 你可以知道你下载了哪些模型，或者你可以挑选自己需要的模型进行安装。

## 如果出现问题！！！

请参考 [issue.md](./issue.md) 进行排查，如果不在 issue 中，请在 issue 中描述你的问题。

我会尽快回复你。

### 3. 运行后端

```shell
just server
```

你可以配置 `config/lab.toml` 的 [package](./settings.md#packagetoml) 来修改后端的行为。

后端可以用于 ASR、TTS、 Translate 、Chat 功能。

### 4. 运行前端

目前有三种前端，分别是：

1. Streamlit WebUI: 它可以下载 b 站视频，做一些字幕提取。
2. Open-LLM-VTuber: 它是一个基于 Live2d+LLM 的 VTuber 项目，默认使用 elaina 的模型。
3. chill with you lo-fi story: 它可以作为一个游戏 Mod 的服务端，提供 tts 服务。

```shell
cd frontend
npm run dev
```

