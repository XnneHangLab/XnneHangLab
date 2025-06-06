## 运行

```shell
uv run acgo { recognize, punc_recover, vad } # 我也知道这个命名真的很诡异, 但是我也不太清楚应该叫啥
```

> [!note]
> 另外这个文档应该被重构, 目前这么写和 acgo -h 没啥区别, 应该按照功能详细描述参数.

## 子命令

### `recognize`

- 描述: 默认的子命令, 可以省略, 用于识别音频的文字和时间戳内容并且保存 srt 字幕.
- 示例:

```shell
xnne@xnne-PC:~/code/XnneHangLab$ uv run acgo -i examples/example1.wav
 INFO  正在检查配置项的合法性~
 任务  识别音频文件
funasr version: 1.2.6.
rtf_avg: 0.003: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 1/1 [00:00<00:00, 40.16it/s]
rtf_avg: 0.055: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 1/1 [00:00<00:00,  2.84it/s]
rtf_avg: 0.050, time_speech:  7.040, time_escape: 0.355: 100%|█████████████████████████████████████████████████████████████████████████████████| 1/1 [00:00<00:00,  2.74it/s]
 INFO  已写入文件: output/example1.srt.
```

- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`， 暂未直接支持视频格式输入。
- **参数列表**:
  - **setting项**： 可以更改配置项(`config/global.toml`)来达到长期的配置效果。
    - `--batch_size_s` int , 批处理大小, 默认值为 300.
    - `--device` str, 计算设备, 可选 `cpu/cuda`.
    - `--output-dir` str, 输出目录, 默认值为 `output/`.
    - `--cache_dir` str, 缓存目录, 默认值为 `.cache/`.
    - `--ffmpeg-path` str, ffmpeg 可执行路径， 默认为 `ffmpeg`， 你也可以使用相对路径下的 `ffmpeg`.
    - `--base-model` str, asr 模型路径, 你可以使用 `just install-model` 来自动安装, 那么可以不用更改配置.
    - `--punc-model` str, punc 模型路径, 你可以使用 `just install-model` 来自动安装, 那么可以不用更改配置.
    - `--vad-model` str, vad 模型路径, 你可以使用 `just install-model` 来自动安装, 那么可以不用更改配置.
    - `--cut` bool, 是否切分长句, 结合 cut_line 使用, 可以把两个字间隔超过 `cut_line` 的句子切分成两句, 默认值为 `false`. 希望短句多的可以开启.
    - `--cut-line` int, 切分长句的阈值, 默认值为 `400`, 单位毫秒, 如果两个字间隔超过 600 ms , 那么这两个字会作为分割线拆分到两句中, 只有在 `--cut` 为 `true` 时才生效.
    - `--combine` bool, 是否合并短句, 结合 combine_line 使用, 可以把两个字间隔小于 `combine_line` 的句子合并成一句, 默认值为 `false`. 注意不可以和 `--cut` 同用.
    - `--combine-line` int, 合并短句的阈值, 默认值为 `400`, 把两个字间隔小于 400 ms 的句子合并成一句, 只有在 `--combine` 为 `true` 时才生效.
    - `--max-sentence-length` int, 配合 combine_line 使用, 约束最长句子的长度(Word Count), 默认值为 `20` , 如果超出这个长度, 那么即使可以符合再次合并的条件, 也不会继续合并. 防止单句过长.
  - **basic项**:
    - `--input-path`, `-i`, str, 输入音频文件路径, 支持单个文件.

### `punc_recover`

- 描述: 恢复 text 的标点.
- 示例:

```shell
xnne@xnne-PC:~/code/XnneHangLab$ uv run acgo punc_recover -i 你好世界
 任务  标点恢复
funasr version: 1.2.6.
rtf_avg: -0.004: 100%|████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 1/1 [00:00<00:00, 240.72it/s]
你好，世界。
```

- 支持的输入格式: `str`
- **参数列表**
  - **setting项**:
    - `--device` str, 计算设备, 可选 `cpu/cuda`.
    - `--punc-model` str, punc 模型路径, 你可以使用 `just install-model` 来自动安装, 那么可以不用更改配置.
  - **basic项**:
    - `--input-text`, `-i`, str, 输入文本内容.

### `vad`

- 描述: 语音活动检测, 返回毫米级别的说话活动起止时间戳.
- 示例:

```shell
xnne@xnne-PC:~/code/XnneHangLab$ uv run acgo vad -i examples/example1.wav
 任务  VAD 语音活动检测
funasr version: 1.2.6.
rtf_avg: 0.005: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 1/1 [00:00<00:00, 27.82it/s]
 INFO  {'key': 'example1', 'timestamp': [[680, 7020]]}
```

- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`
- **参数列表**
  - **setting项**:
    - `--device` str, 计算设备, 可选 `cpu/cuda`.
    - `--vad-model` str, vad 模型路径, 你可以使用 `just install-model` 来自动安装, 那么可以不用更改配置.
  - **basic项**:
    - `--input-path`, `-i`, str, 输入音频文件路径, 支持单个文件.
