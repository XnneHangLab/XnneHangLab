# 🚀 FastAPI 接口说明（fastapi.md）

本项目后端基于 **FastAPI**，提供：

- 🎙️ ASR（FunASR / Whisper）
- 🗣️ TTS（GPT-SoVITS / GPT-SoVITS v2）
- 🌍 翻译（DeepLX）

> 🧭 默认地址：`http://127.0.0.1:12393`  
> 🔎 Swagger：`/docs`（推荐）｜ReDoc：`/redoc`  
> ✅ 示例命令 **全部以项目 Justfile 为准**（不再“自己编” curl），因为 `./examples/*` 也是项目的一部分。

---

## ▶️ 启动服务

推荐用 Justfile：

```bash
just server
```

---

## 🌳 路由总览（tree view）

```text
/
├─ /docs
├─ /redoc
│
├─ /asr
│  ├─ /funasr/with_punc      POST   (multipart/form-data: file)
│  ├─ /funasr/no_punc        POST   (multipart/form-data: file)
│  ├─ /funasr/vad            POST   (multipart/form-data: file)
│  └─ /whisper               POST   (multipart/form-data: file)
│
├─ /tts
│  ├─ /gptsovits             POST   (application/json)
│  └─ /gptsovitsv2/tts        GET   (query params, returns audio)
│
└─ /translate
   └─ /deeplx                POST   (application/json)
```

---

## 🧪 一键自测（直接用 Justfile）

你可以在服务启动后，直接跑这些命令验证接口是否工作（与项目 `Justfile` 保持一致）：

```bash
just test-asr
just test-asr-no-punc
just test-vad
just test-whisper
just test-gsv
just test-gsv-v2
just test-deeplx
```

> 💡 如果你刚拉完代码/换了 Key：可以用 `just key` 同步 API Key（Justfile 中的 recipe：`uv run scripts/sync_apikey.py`）。

---

## 📦 通用约定

### 🎧 音频上传字段
- 统一使用表单字段名：`file`
- 格式：`multipart/form-data`

### ⏱️ 时间戳单位
- ASR / VAD 的 `timestamp` 通常是 **毫秒 ms**
- 结构：`[[start_ms, end_ms], ...]`

---

## 🎙️ ASR

### ✅ FunASR：带标点识别
`POST /asr/funasr/with_punc`

**推荐测试（Justfile）：**
```bash
just test-asr
```

**Justfile 实际执行内容：**
```bash
curl -X POST "http://localhost:12393/asr/funasr/with_punc" -F "file=@./examples/example3.opus"
```

---

### 🧩 FunASR：不带标点识别
`POST /asr/funasr/no_punc`

**推荐测试（Justfile）：**
```bash
just test-asr-no-punc
```

**Justfile 实际执行内容：**
```bash
curl -X POST "http://localhost:12393/asr/funasr/no_punc" -F "file=@./examples/example3.opus"
```

---

### 🔍 FunASR：VAD（语音活动检测）
`POST /asr/funasr/vad`

**推荐测试（Justfile）：**
```bash
just test-vad
```

**Justfile 实际执行内容：**
```bash
curl -X POST "http://localhost:12393/asr/funasr/vad" -F "file=@./examples/example3.opus"
```

---

### 🌀 Whisper：识别（含 segments）
`POST /asr/whisper`

**推荐测试（Justfile）：**
```bash
just test-whisper
```

**Justfile 实际执行内容：**
```bash
curl -X POST "http://localhost:12393/asr/whisper" -F "file=@./examples/example3.opus"
```

---

## 🗣️ TTS

### 🧙 GPT-SoVITS（JSON → base64 音频）
`POST /tts/gptsovits`

**推荐测试（Justfile）：**
```bash
just test-gsv
```

**Justfile 实际执行内容（保持原样）：**
```bash
curl -X POST "http://127.0.0.1:12393/tts/gptsovits" \
-H "Content-Type: application/json" \
-d '{ \
	"text": "それでは問題です。澄み渡った青空をゆく、そこに人がいたのなら間違いなく誰もが振り返り、ため息をこぼしてしまうほどの美貌の魔女は、いったい誰でしょう？", \
	"character": "elaina", \
	"text_language": "ja", \
	"ref_audio_path": "./models/gptsovits/elaina/elaina.wav" \
}' \
-o response.json \
&& uv run python -c "import json, base64; data=json.load(open('response.json')); open('output.mp3', 'wb').write(base64.b64decode(data['audio_byte']))"
rm response.json
```

> 📌 这个测试会生成 `output.mp3`（从返回的 `audio_byte` base64 解码）。

---

### 🧪 GPT-SoVITS v2（Query → 直接返回音频）
`GET /tts/gptsovitsv2/tts`

**推荐测试（Justfile）：**
```bash
just test-gsv-v2
```

**Justfile 实际执行内容：**
```bash
curl -G "http://127.0.0.1:12393/tts/gptsovitsv2/tts" --data-urlencode "text=こんにちは、お元気ですか？今日も一緒に頑張りましょう！" --data-urlencode "text_lang=ja" --data-urlencode "ref_audio_path=Voice_MainScenario_27_016.wav" --data-urlencode "prompt_text=君が集中した時のシータ波を検出して、リンクをつなぎ直せば元通りになるはず。" --data-urlencode "prompt_lang=ja" --data-urlencode "speed_factor=1.0" -o tts.wav
```

> 📌 这个测试会把返回音频保存为 `tts.wav`。

---

## 🌍 翻译

### 🔤 DeepLX 翻译
`POST /translate/deeplx`

**推荐测试（Justfile）：**
```bash
just test-deeplx
```

**Justfile 实际执行内容（保持原样）：**
```bash
curl -X POST "http://127.0.0.1:12393/translate/deeplx" \
-H "Content-Type: application/json" \
-d '{ \
	"text": "それでは問題です。澄み渡った青空をゆく、そこに人がいたのなら間違いなく誰もが振り返り、ため息をこぼしてしまうほどの美貌の魔女は、いったい誰でしょう？", \
	"source_language": "Auto", \
	"target_language": "ZH" \
}' \
```
