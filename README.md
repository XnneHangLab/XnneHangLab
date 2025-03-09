<p align="center">
       <a href="https://github.com/modelscope/FunASR?tab=readme-ov-file"><img alt="funasr" src="https://camo.githubusercontent.com/eda774e3f1b9215478715fedecf8587062f33f37864ff904008d24117e18bc43/68747470733a2f2f7376672d62616e6e6572732e76657263656c2e6170702f6170693f747970653d6f726967696e2674657874313d46756e4153522546302539462541342541302674657874323d2546302539462539322539362532304125323046756e64616d656e74616c253230456e642d746f2d456e642532305370656563682532305265636f676e6974696f6e253230546f6f6c6b69742677696474683d383030266865696768743d323130" width="600" height="150"></a>
   <br/>
   <a href="https://python.org/" target="_blank"><img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/moelib?logo=python&style=flat-square"></a>
   <br/>
   <a href="https://github.com/astral-sh/uv"><img alt="uv" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=flat-square"></a>
   <a href="https://github.com/astral-sh/ruff"><img alt="ruff" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square"></a>
   <a href="https://gitmoji.dev"><img alt="Gitmoji" src="https://img.shields.io/badge/gitmoji-%20😜%20😍-FFDD67?style=flat-square"></a>
   <br/>
</p>


# 这是什么？

这是一个基于 [Funasr](https://github.com/modelscope/FunASR?tab=readme-ov-file), 将 wav 文件转换为 srt 字幕文件的工具。

# 如何使用？(从安装开始~)

以安装 cpu 版本为例。(目前也暂时只有 cpu 版本 =_= )

## 克隆本仓库:

```shell
git clone https://github.com/MrXnneHang/Auto-Caption-Generate-Offline@v2.4-cpu
cd Auto-Caption-Generate-Offline
```

## 下载必要的模型文件

参见 [models/download.md](https://github.com/MrXnneHang/Auto-Caption-Generate-Offline/blob/v2.4-cpu/models/download.md) 进行手动下载.<br>

或者直接使用 `modelscope`.<br>

```shell
pip install modelscope
```

vad 模型:<br>

```shell
cd models/
modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir ./speech_fsmn_vad_zh-cn-16k-common-pytorch
```

punc 模型:<br>

```shell
modelscope download --model iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch --local_dir ./punc_ct-transformer_zh-cn-common-vocab272727-pytorch
```

asr 模型:<br>

```shell
modelscope download --model iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch --local_dir ./speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
```

## 运行:

```shell
uv run acgo -i test.wav -o test.srt
```

建议使用 uv 运行。不需要手动配置环境。<br>

[安装uv](https://docs.astral.sh/uv/getting-started/installation/)<br>

或者你可以使用 pip 从源码安装:<br>

```shell
pip install git+https://github.com/MrXnneHang/Auto-Caption-Generate-Offline@v2.4-cpu
```

## 配置文件（更灵活的字幕配置）:

你可以把配置文件放在工作目录下或者 `~/.config/acgo.yaml`.<br>

大部分参数都有注释。<br>

这里讲一下一些特别的:<br>

### `cut`&`cut_line`&`combine`&`combine_line`的联动: 自由调整字幕速度节奏

你可以通过设置它们来调整你字幕中每一句的长度，即字幕速度。<br>

如果你希望在快节奏视频（如游戏解说）中字幕速度快一些，短一些，那么请把`cut`设置为`True`，`cut_line`设置得略微小一些，比如`300`,单位是`ms`，当两个字幕之间的间隔大于`300ms`时，会自动切割。<br>

如果你希望在慢节奏视频（如课程）中字幕慢一点长一点完整一点，那么请把`combine`设置为`True`，`combine_line`设置得略微大一些，比如`1000`,单位是`ms`，当两个字幕之间的间隔小于`1000ms`时，会自动合并。当然为了防止过长，你可以通过`max_sentence_length`(单位是字)来限制最长句子长度。<br>

可以都设置为 false,即直接按照模型生成的字幕写入 srt，但是不能同时设置为 true, 会相互抵消。<br>

### `need_punc`: 是否需要标点恢复

对于字幕很长的比如上面使用了 combine 的用户，那么请打开，它会在生成字幕的时候自动恢复标点。<br>

你并不希望30字的一句话没有一个标点吧？<br>

### `hot_words_path`: 热词路径

热词功能可以抑制口音带来的口胡，比如一些音近词。`西式`和`西市`, 当你在热词中加入`西市`，那么模型会优先生成`西市`而不是`西式`。在特定任务中很有用。<br>

hot_words 格式:<br>

```txt
请不要加入标点符号
以换行分隔热词
依孜镇
卡落斯
新作
```

## RoadMap:

- [ ] 创建 cuda 版本分支
- [ ] config 的自动创建
- [ ] 简单 gui 的支持.
- [ ] mp4 的支持.(需要 ffmpeg)

## 如何参与到开发:

参见[CONTRIBUTING.md](https://github.com/MrXnneHang/Auto-Caption-Generate-Offline/blob/v2.4-cpu/CONTRIBUTING.md)<br>