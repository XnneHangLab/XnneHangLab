key:
  uv run scripts/sync_apikey.py  # 同步 API Key

start:
  uv lock
  uv sync
  uv run get_root
  uv run streamlit run src/lab/ui.py --server.port 8051

clean-venv:
  # 如果在 windows 上删不干净，可以运行 `FileLocksmithCLI.exe --kill "D:\tmp\XnneHangLab\.venv"`
  rm ./.venv -rf

dev:
    # 删除所有构建产物和缓存 / 二次操作防止缓存问题恢复代码
    rm -rf packages/*/dist
    rm -rf packages/*/__pycache__
    rm -rf packages/*/*.egg-info
    uv build packages/yutto
    uv build packages/wexpect-uv
    uv lock --no-cache
    uv run get_root
    uv run streamlit run src/lab/ui.py --server.port 8000

dev-clean:
  rm packages/yutto/dist -rf
  rm packages/wexpect-uv/dist -rf

# Server Start

mcp-server:
  uv run src/lab/mcp/server/timeemi.py & \
  uv run src/lab/mcp/server/vision.py & \

server:
  uv run get_root
  uv run run_server.py

db-server:
  uv run uvicorn src.lab.database.main:app --reload --host localhost --port 8000

# API Router Test

test-asr:
  curl -X POST "http://localhost:12393/audio/asr" -F "file=@./examples/example3.opus"

test-asr-no-punc:
  curl -X POST "http://localhost:12393/audio/asr_no_punc" -F "file=@./examples/example3.opus"

test-vad:
  curl -X POST "http://localhost:12393/audio/vad" -F "file=@./examples/example3.opus"

test-gsv:
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

test-gsv-v2:
    curl -G "http://127.0.0.1:12393/tts/gptsovitsv2/tts" --data-urlencode "text=こんにちは、お元気ですか？今日も一緒に頑張りましょう！" --data-urlencode "text_lang=ja" --data-urlencode "ref_audio_path=Voice_MainScenario_27_016.wav" --data-urlencode "prompt_text=君が集中した時のシータ波を検出して、リンクをつなぎ直せば元通りになるはず。" --data-urlencode "prompt_lang=ja" --data-urlencode "speed_factor=1.0" -o tts.wav


test-deeplx:
	curl -X POST "http://127.0.0.1:12393/translate/deeplx" \
	-H "Content-Type: application/json" \
	-d '{ \
		"text": "それでは問題です。澄み渡った青空をゆく、そこに人がいたのなら間違いなく誰もが振り返り、ため息をこぼしてしまうほどの美貌の魔女は、いったい誰でしょう？", \
		"source_language": "Auto", \
		"target_language": "ZH" \
	}' \


# deploy

install-model:
  uv lock
  uv sync
  just install-nltk

  just install-funasr-model
  just install-whisper
  just install-embedding-model
  just install-sensevoice
  just install-bert-model
  just install-gsv-model

install-nltk:
  uv run python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"

install-funasr-model:
  uv lock
  uv sync

  # ASR with hotwords
  uv run modelscope download --model iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch --local_dir ./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
  uv run modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir ./models/speech_fsmn_vad_zh-cn-16k-common-pytorch
  uv run modelscope download --model iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch --local_dir ./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch

install-whisper:
  uv lock
  uv sync
  # tiny.pt
  uv run scripts/download.py --url https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt --filename tiny.pt --output-dir ./models/whisper
  # large-v3-turbo.pt
  uv run scripts/download.py --url https://www.modelscope.cn/models/iic/Whisper-large-v3-turbo/resolve/master/large-v3-turbo.pt --filename large-v3-turbo.pt --output-dir ./models/whisper

install-embedding-model:
  uv lock
  uv sync
  uv run modelscope download --model iic/nlp_gte_sentence-embedding_chinese-base --local_dir ./models/nlp_gte_sentence-embedding_chinese-base

install-sensevoice:
  uv lock
  uv sync
  # SenseVoiceSmall
  uv run modelscope download --model iic/SenseVoiceSmall --local_dir ./models/SenseVoiceSmall

install-bert-model:
  uv lock
  uv sync
  uv run modelscope download --model pengzhendong/chinese-hubert-base --local_dir ./models/chinese-hubert-base pytorch_model.bin
  uv run modelscope download --model dienstag/chinese-roberta-wwm-ext-large --local_dir ./models/chinese-roberta-wwm-ext-large  \
  pytorch_model.bin added_tokens.json config.json configuration.json README.md special_tokens_map.json tokenizer_config.json tokenizer.json
  # 这里不能用 --exclude 同时排除 tf_model.h5 和 flax_model.msgpack，多次 exclude 只会保留最后一个，所以这里指定了所有需要的文件

install-gsv-model:
  uv lock
  uv sync
  uv run modelscope download --model xnnehang/elaina-gsv-v2 --local_dir ./models/gptsovits/elaina

# Code Quality Check

fmt: # 似乎不会检查被 .gitignore 忽略的文件
  uv run ruff check --fix --select I . --exclude packages
  uv run ruff format . --exclude packages

lint:
  uv run pyright src/lab tests
  uv run ruff check . --exclude packages

fmt-docs:
  prettier --ignore-path .prettierignore --write '**/*.md'

test:
  uv run pytest tests -vvv

# CI-workflow

ci-install:
  uv lock
  uv sync

ci-test:
  just test

ci-fmt-check:
  just fmt

ci-lint:
  just lint