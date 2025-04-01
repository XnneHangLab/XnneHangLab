<a href="https://xnnehang.top/">

<div align="center">
    <img src="https://fastly.jsdelivr.net/gh/MrXnneHang/blog_img/BlogHosting/img/25/02/202503312014744.svg" alt="魔女の实验室" width="270" height="180">
</div>
<h1 align="center">XnneHangLab</h1>
</a>
<br/>
<div align="center">
<a href="https://github.com/astral-sh/uv"><img alt="uv" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=flat-square"></a>
<a href="https://github.com/astral-sh/ruff"><img alt="ruff" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square"></a>
<a href="https://gitmoji.dev"><img alt="Gitmoji" src="https://img.shields.io/badge/gitmoji-%20😜%20😍-FFDD67?style=flat-square"></a>
<a href="https://pytorch.org/" target="_blank"><img alt="PyTorch" src="https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=flat-square&logo=pytorch&logoColor=white"></a>
<a href="https://github.com/modelscope/FunASR" target="_blank"><img alt="FunASR" src="https://img.shields.io/badge/FunASR-%23F0A4A0.svg?style=flat-square&logo=github&logoColor=white"></a><a href="https://streamlit.io/" target="_blank"><img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-%23FF4B4B.svg?style=flat-square&logo=streamlit&logoColor=white"></a>
<br/>
</div>
<p align="center"> <a href="./README_en.md"><b>English Documentation </b></a> </p>

<p align="center">
 魔女の实验室
</p>

<p align="center">
<a href='https://xnnehang.top/' style='font-size: 20px;'><strong>文档网站(等等噢)</strong></a> ·
<a href='https://space.bilibili.com/556737824'><strong>bilibili视频教程(再等等噢)</strong></a>
</p>
<p align="center">
  <a href="#功能"><strong>功能</strong></a> ·
  <a href="#演示"><strong>演示</strong></a> ·
  <a href="#本地部署运行"><strong>本地部署运行</strong></a>
</p>

<br/>

## 它为什么诞生

我对它的期望是一个满足我日常音频所需的完整的工作流，主要有:

**做视频:** 视频字幕生成 -> 视频字幕速度调节和编辑 -> 字幕内嵌或者导出

**啃生肉提高日语水平** b站视频下载 -> 视频字幕生成 -> 视频字幕翻译

**tts/sts 数据集制作:** 音频字幕生成 -> 自动裁剪音频 -> 响度匹配 -> 降噪 -> 字幕再次生成

**tts/sts 微调和语音生成:** 可能会把以前玩过的 Bert-ViTS2 集成进来，同样，也是做视频用。

## 为什么叫魔女の实验室

我在写这个项目的时经常想到伊蕾娜她小时候认真学习魔法的样子。

我大概也是以那种心态在写这个项目吧。不知道后面能不能直接把这个当毕设了。

## 功能

- [**待办事项：** A To-Do-List Built by Streamlit.](https://github.com/MrXnneHang/Streamlit-To-Do-List?tab=readme-ov-file)

由于我总是忘记之后要什么，所以做了一个 To-Do-List 来提醒自己。分短期和长期任务，长期任务也可以作为 RoadMap。

- [**字幕生成（本地运行）:** 基于 Funasr, 支持热词，支持字幕速度调节和编辑](https://xnnehang.top/posts/software/Auto_Caption_Generater_Offline_v2_4)

最近正在支持 SenseVoice 的时间检测，以及视频输入的 GUI 版本还在赶来的路上。

**Building...**

- [**yutto-uiya:** 一个 bilibili 视频下载器，基于 yutto 开发的 WebUI](https://github.com/MrXnneHang/yutto-uiya)

正在用 Streamlit 重构 WebUI ，之后就可以直接集成进来。致力于从视频下载到音频处理以及字幕生成一条龙服务。

## 演示

[从我的网站访问: **xlab.xnnehang.top**](https://xlab.xnnehang.top)

我用 frp 和 一个外国的服务器把该项目部署到了我家的台式机并且可以通过网站访问。你可以在这里轻度体验。

近期可能网站经常下线，等到开发到稳定版本了应该才会比较稳定。

下面是一些截图。

![todo](https://fastly.jsdelivr.net/gh/MrXnneHang/blog_img/BlogHosting/img/25/02/202503312105787.png)

![audio-recognize](https://fastly.jsdelivr.net/gh/MrXnneHang/blog_img/BlogHosting/img/25/02/202503312004227.png)

## 本地部署

### 0.前置

[**uv**](https://docs.astral.sh/uv/) 是本项目的包管理工具，它让你免于手动配置和调试环境。你可以从[安装指南](https://docs.astral.sh/uv/getting-started/installation/)找到合适的安装方式～

[**just**](https://github.com/casey/just) 是一款用 rust 编写的简单易用的命令执行工具，它可以让原本复杂的命令运行变得简单。安装方法请参考[它的文档](https://github.com/casey/just#installation)。该项非必须， Windows 比较难安装 just , 可以跳过。后续使用 bat 脚本替代即可。

**ps:** windows 用户也可以等待网盘的整合包。

### 1.从 Release 页面下载源码（XnneHangLab.zip）

[Release 页面](https://github.com/MrXnneHang/Auto-Caption-Generator-Offline/releases)

建议下载最新，或者根据功能需求选择。

因为目前该项目处于高速开发期，我并不是以 PR 的形式提交代码，而是框框地直接 commit ，所以每天可能都有五六个甚至十几个 commit 。其中有一些新功能未成型，或者容易有一些 bug 。所以除非你想要参与到开发，不然并不建议从 [dev 分支](https://github.com/MrXnneHang/XnneHangLab) 进行构建。

### 2. 自动安装依赖并下载必要模型权重文件

如果你有 just:

```shell
just install-model
```

过程可能较久，因为需要先安装 python 环境，然后再下载模型， 模型和环境都不小, 建议可以先构建 cpu 版本进行功能预览，等有性能和批处理需求了再构建 gpu 版本的 torch。

更改 pyproject.toml 的这几行即可：

```toml
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

默认 windows 下是 pytorch-cu118 , linux 和 mac 下是 pytorch-cpu 。

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
Downloading Model from https://www.modelscope.cn to directory: /home/xnne/code/XnneHangLab/models/speech_fsmn_vad_zh-cn-16k-common-pytorch
2025-03-31 20:41:34,048 - modelscope - WARNING - Model revision not specified, use revision: v2.0.4
uv run modelscope download --model iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch --local_dir ./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
Downloading Model from https://www.modelscope.cn to directory: /home/xnne/code/XnneHangLab/models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
2025-03-31 20:41:36,349 - modelscope - WARNING - Model revision not specified, use revision: v2.0.9
# SenseVoiceSmall
uv run modelscope download --model iic/SenseVoiceSmall --local_dir ./models/SenseVoiceSmall
Downloading Model from https://www.modelscope.cn to directory: /home/xnne/code/XnneHangLab/models/SenseVoiceSmall
```

如果你是 Windows 并且没有 just , 那么也可以通过手动运行下列命令来安装模型:

```shell
uv lock
uv sync

# ASR with hotwords
uv run modelscope download --model iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch --local_dir ./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
uv run modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir ./models/speech_fsmn_vad_zh-cn-16k-common-pytorch
uv run modelscope download --model iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch --local_dir ./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch

# SenseVoiceSmall
uv run modelscope download --model iic/SenseVoiceSmall --local_dir ./models/SenseVoiceSmall
```

可以通过阅读 `justfile` 得到。

### 3.运行程序

```shell
just start
```

之后进入弹出的 URL 即可:

```shell
(xnnehanglab) xnne@xnne-PC:~/code/XnneHangLab$ just start
uv lock
Resolved 106 packages in 6ms
uv sync
Resolved 106 packages in 6ms
Audited 100 packages in 0.31ms
uv run get_root
uv run streamlit run src/uiya/ui.py

  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.123.109:8501
```

## 使用手册

参见那个还没出来的文档网站 =-= 。

## RoadMap

- [ ] 音频处理的批处理支持
- [ ] 音频字幕编辑和微调
- [ ] SenseVoice with TimeStamp 模型选项支持
- [ ] 视频识别模块
- [ ] yutto-uiya 的移重构 bilibili 视频下载 new package

## 引用的仓库

- [**FunASR:** A Fundamental End-to-End Speech Recognition Toolkit and Open Source SOTA Pretrained Models, Supporting Speech Recognition, Voice Activity Detection, Text Post-processing etc.](https://github.com/modelscope/FunASR?tab=readme-ov-file)
- [**Streamlit** — A faster way to build and share data apps.](https://github.com/streamlit/streamlit)
- [**yutto:** 🧊 一个可爱且任性的 B 站视频下载器](https://github.com/yutto-dev/yutto)
- [**Chenyme-AAVT:** 这是一个全自动（音频）视频翻译项目。利用Whisper识别声音，AI大模型翻译字幕，最后合并字幕视频，生成翻译后的视频。](https://github.com/Chenyme/Chenyme-AAVT)

## 如何参与到开发:

详细参见： [CONTRIBUTING.md](https://github.com/MrXnneHang/XnneHangLab/blob/dev/CONTRIBUTING.md)

非常欢迎各位以任何形式的贡献，包括， bug 反馈，使用体验优化，第三方库和模型更新提醒，合理有益的功能需求等等。
