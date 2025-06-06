## 运行

```shell
just server # 使用 just
uv run uvicorn src.lab.api_server:app --reload --host localhost --port 8000 # 直接运行
```

## route

### `/rec-audio`

- 描述: 识别音频的文字内容
- 方法: `curl -X POST "http://localhost:8000/rec-audio" -F "file=@./examples/example3.opus"`
- 响应示例: `{"processing_time":0.42760634422302246,"text":"那年，长街春意正浓，策马同游。"}`
- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`

### `/vad-audio`

- 描述: 语音活动(是否有人在说话)检测, 返回毫米级别的起止时间戳
- 方法: `curl -X POST "http://localhost:8000/vad-audio" -F "file=@./examples/example3.opus"`
- 响应示例: `{"processing_time":0.027205705642700195,"time_stamp":[[680,7020]]}`
- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`
