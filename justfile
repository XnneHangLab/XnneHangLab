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

test-tts:
  curl -X POST   -H "Content-Type: application/json"   -d '{"text": "我写了两个杀人推理短篇，他们互为答案（下）鲅鱼村杀人疑案。"}'   -o output.opus   http://localhost:12393/tts/direct


test-rec-audio:
  curl -X POST "http://localhost:8000/rec-audio" -F "file=@./examples/example3.opus"

test-vad-audio:
  curl -X POST "http://localhost:8000/vad-audio" -F "file=@./examples/example3.opus"

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