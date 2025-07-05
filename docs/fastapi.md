## 模型下载

参见 [./deploy.md](./deploy.md) 文档。

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

## `/tts/bert-vits`

- 描述: 调用 Bert-VITS2 合成音频
- 方法&&响应示例:
```shell
xnnehanglab➜  VtuberLab git:(rest-api-design) ✗ just test-bert-vits 
  curl -X POST "http://localhost:12393/tts/bert_vits" \
       -H "Content-Type: application/json" \
       -d '{"text": "我写了两个杀人推理短篇，他们互为答案（下）鲅鱼村杀人疑案。","audio_type":"opus"}' \
       -o response.json
  # 第二步：提取并解码音频数据
  python -c "import json, base64; data=json.load(open('response.json')); open('output.opus', 'wb').write(base64.b64decode(data['audio_byte']))"
  # 清理中间文件
  rm response.json

xnnehanglab➜  VtuberLab git:(rest-api-design) ✗ ls output.opus 
output.opus
```

## `/tts/gpt-sovits`

- 描述: 调用 GPT-SoVITS 合成音频, 需要开启 packages.toml 中的 `gpt-sovits` 功能.
- 方法&&响应示例:
```shell
xnnehanglab➜  VtuberLab git:(add-gpt-sovits) ✗ just test-gsv
curl -X POST "http://127.0.0.1:12393/tts/gptsovits" -H "Content-Type: application/json" -d '{ "text": "それでは問題です。澄み渡った青空をゆく、そこに人がいたのなら間違いなく誰もが振り返り、ため息をこぼしてしまうほどの美貌の魔女は、いったい誰でしょう？", "character": "elaina", "text_language": "ja", "ref_audio_path": "/home/xnne/code/Chatter/VtuberLab/models/gptsovits/elaina/elaina.wav" }' -o response.json && python -c "import json, base64; data=json.load(open('response.json')); open('output.mp3', 'wb').write(base64.b64decode(data['audio_byte']))"
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  729k  100  729k  100   372  46126     22  0:00:16  0:00:16 --:--:--  174k
rm response.json

xnnehanglab➜  VtuberLab git:(add-gpt-sovits) ✗ ls output.mp3 
output.mp3
```

support json body:

```json
{
    "method": "POST",
    "body": {
        "text": "${speakText}",
        "ref_audio_path": "${refAudioPath}",
        "text_language": "${textLanguage}",
        "speed": ${speed},
        "temperature": ${temperature},
    }
}
```

## `translate/deeplx`

- 描述: 使用 deeplx 翻译文本,需要预先在 agent.toml 里填写 API KEY.
- 方法: `curl -X POST "http://127.0.0.1:12393/translate/deeplx" -H "Content-Type: application/json" -d '{ "text": "それでは問題です。澄み渡った青空をゆく、そこに人がいたのなら間違いなく誰もが振り返り、ため息をこぼしてしまうほどの美貌の魔女は、いったい誰でしょう？", "source_language": "JA", "target_language": "ZH" }'`
- 响应示例: `{"code":200,"message":"success","source_text":"JA","target_text":"现在问题来了。在湛蓝的天空中穿行的美丽女巫是谁，如果有一个人在那里，一定会让所有人回首叹息？"}%     `
