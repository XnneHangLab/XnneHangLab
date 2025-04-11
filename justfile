VERSION := `uv run scripts/get-version.py src/lab/__version__.py`


start:
  uv lock
  uv sync
  uv run get_root
  uv run streamlit run src/lab/ui.py

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



fmt:
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