## 运行

```shell
just server # 使用 just
uv run uvicorn src.lab.api_server:app --reload --host localhost --port 8000 # 直接运行
```

## route

### `/rec-audio`

- 描述: 识别音频的文字内容
- 方法: `curl -X POST "http://localhost:8000/rec-audio" -F "file=@./examples/example3.opus"`
- 响应示例: `{"key":"example3","processing_time":0.8867478370666504,"text":"那年，长街春意正浓，策马同游。","time_stamp":[[910,1130],[1130,1370],[1490,1730],[1950,2190],[2370,2610],[2690,2930],[3030,3270],[3850,4090],[5430,5670],[5750,5990],[6070,6310],[6470,6795]]}`
- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`

### `/vad-audio`

- 描述: 语音活动(是否有人在说话)检测, 返回毫米级别的起止时间戳
- 方法: `curl -X POST "http://localhost:8000/vad-audio" -F "file=@./examples/example3.opus"`
- 响应示例: `{"key":"example3","processing_time":0.29256510734558105,"timestamp":[[680,7020]],"audio_length":7046}`
- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`
