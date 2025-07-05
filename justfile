start:
  uv lock
  uv sync
  uv run get_root
  uv run streamlit run src/lab/ui.py --server.port 8051

dev-clean:
  rm packages/yutto/dist -rf
  rm packages/wexpect-uv/dist -rf

server:
  uv run run_server.py

db-server:
  uv run uvicorn src.lab.database.main:app --reload --host localhost --port 8000

test-bert-vits:
  curl -X POST "http://localhost:12393/tts/bert_vits" \
       -H "Content-Type: application/json" \
       -d '{"text": "我写了两个杀人推理短篇，他们互为答案（下）鲅鱼村杀人疑案。","audio_type":"opus"}' \
       -o response.json
  # 第二步：提取并解码音频数据
  python -c "import json, base64; data=json.load(open('response.json')); open('output.opus', 'wb').write(base64.b64decode(data['audio_byte']))"
  # 清理中间文件
  rm response.json

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
		"ref_audio_path": "/home/xnne/code/Chatter/VtuberLab/models/gptsovits/elaina/elaina.wav" \
	}' \
	-o response.json \
	&& python -c "import json, base64; data=json.load(open('response.json')); open('output.mp3', 'wb').write(base64.b64decode(data['audio_byte']))"
	rm response.json


test-deeplx:
	curl -X POST "http://127.0.0.1:12393/translate/deeplx" \
	-H "Content-Type: application/json" \
	-d '{ \
		"text": "それでは問題です。澄み渡った青空をゆく、そこに人がいたのなら間違いなく誰もが振り返り、ため息をこぼしてしまうほどの美貌の魔女は、いったい誰でしょう？", \
		"source_language": "Auto", \
		"target_language": "ZH" \
	}' \

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

install-model:
  uv lock
  uv sync

  # ASR with hotwords
  uv run modelscope download --model iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch --local_dir ./models/punc_ct-transformer_zh-cn-common-vocab272727-pytorch
  uv run modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir ./models/speech_fsmn_vad_zh-cn-16k-common-pytorch
  uv run modelscope download --model iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch --local_dir ./models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch

install-sensevoice:
  uv lock
  uv sync
  # SenseVoiceSmall
  uv run modelscope download --model iic/SenseVoiceSmall --local_dir ./models/SenseVoiceSmall

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

ci-install:
  uv lock
  uv sync


ci-test:
  just test

ci-fmt-check:
  just fmt

ci-lint:
  just lint