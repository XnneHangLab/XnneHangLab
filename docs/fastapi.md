## 模型下载

asr, vad:

```shell
just install-model
```

bert-vits:

建议手动下载:

```shell
xnnehanglab➜  VtuberLab git:(copy-open-llm-vtuber) ✗ ls models 
BERT-VITS2.3
```


## 运行

```shell
just server # 使用 just
uv run uvicorn src.lab.api_server:app --reload --host localhost --port 12393 # 直接运行
```

## 路由

### `/audio/asr`

- 描述: 识别音频的文字内容
- 方法: `curl -X POST "http://localhost:12393/audio/asr" -F "file=@./examples/example3.opus"`
- 响应示例: `{"key":"example3","processing_time":0.8376491069793701,"text":"那年，长街春意正浓，策马同游。","time_stamp":[[910,1130],[1130,1370],[1490,1730],[1950,2190],[2370,2610],[2690,2930],[3030,3270],[3850,4090],[5430,5670],[5750,5990],[6070,6310],[6470,6795]]}`
- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`

### `/audio/vad`

- 描述: 语音活动(是否有人在说话)检测, 返回毫米级别的起止时间戳
- 方法: `curl -X POST "http://localhost:12393/audio/vad" -F "file=@./examples/example3.opus"`
- 响应示例: `{"key":"example3","processing_time":0.29256510734558105,"timestamp":[[680,7020]],"audio_length":7046}`
- 支持的音频格式: `wav`, `mp3`, `opus`, `flac`, `ogg`, `m4a`, `aac`

## `/tts/direct`

- 描述: 调用 Bert-VITS2 合成音频
- 方法: `curl -X POST   -H "Content-Type: application/json"   -d '{"text": "我写了两个杀人推理短篇，他们互为答案（下）鲅鱼村杀人疑案。"}'   -o output.opus   http://localhost:12393/tts/direct`
- 响应示例:
```shell
xnnehanglab➜  VtuberLab git:(copy-open-llm-vtuber) ✗ just test-tts
curl -X POST   -H "Content-Type: application/json"   -d '{"text": "我写了两个杀人推理短篇，他们互为答案（下）鲅鱼村杀人疑案。"}'   -o output.opus   http://localhost:12393/tts/direct
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 46580    0 46481  100    99  16640     35  0:00:02  0:00:02 --:--:-- 16677

xnnehanglab➜  VtuberLab git:(copy-open-llm-vtuber) ✗ ls
bert   chat_history  CONTRIBUTING.md  examples       justfile  logs    output       packages  __pycache__     README.md      src     temp   UPDATELOG.md
cache  config        docs             hot_words.txt  LICENCE   models  output.opus  prompts   pyproject.toml  run_server.py  static  tests  uv.lock
```