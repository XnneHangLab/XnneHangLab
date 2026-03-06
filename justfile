key:
  uv run scripts/sync_apikey.py  # 同步 API Key

list-model: # 列出配置项中填写 api_key 的模型列表
  uv run get_root
  uv run scripts/list_model_name.py

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
  uv run src/lab/mcp/server/timeemi_server.py & \
  uv run src/lab/mcp/server/vision_server.py & \
  uv run src/lab/mcp/server/tool_server.py & \

server:
  uv run get_root
  uv run run_server.py

db-server:
  uv run uvicorn src.lab.database.main:app --reload --host localhost --port 8000

# API Router Test

test-asr:
  curl -X POST "http://localhost:12393/asr/funasr/with_punc" -F "file=@./examples/example3.opus"

test-asr-no-punc:
  curl -X POST "http://localhost:12393/asr/funasr/no_punc" -F "file=@./examples/example3.opus"

test-vad:
  curl -X POST "http://localhost:12393/asr/funasr/vad" -F "file=@./examples/example3.opus"

test-whisper:
  curl -X POST "http://localhost:12393/asr/whisper" -F "file=@./examples/example3.opus"

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
    curl -G "http://127.0.0.1:12393/tts/gptsovitsv2/tts" --data-urlencode "text=こんにちは、お元気ですか？今日も一緒に頑張りましょう！" --data-urlencode "text_lang=ja" --data-urlencode "ref_audio_path=elaina.wav" --data-urlencode "prompt_text=君が集中した時のシータ波を検出して、リンクをつなぎ直せば元通りになるはず。" --data-urlencode "prompt_lang=ja" --data-urlencode "speed_factor=1.0" -o tts.wav


test-deeplx:
	curl -X POST "http://127.0.0.1:12393/translate/deeplx" \
	-H "Content-Type: application/json" \
	-d '{ \
		"text": "それでは問題です。澄み渡った青空をゆく、そこに人がいたのなら間違いなく誰もが振り返り、ため息をこぼしてしまうほどの美貌の魔女は、いったい誰でしょう？", \
		"source_language": "Auto", \
		"target_language": "ZH" \
	}' \



test-qwen-tts-health server='http://localhost:12393':
  uv run python scripts/test_qwen_tts_client.py --server {{ server }} --mode health

test-qwen-tts-non-stream server='http://localhost:12393' ref_audio='5_vocals_cut.wav' ref_text='そうそう、この間気分転換に料理したんだ。テスト勉強のモチベを上げるためにも、自分の好物を作ることにしたんだ。あれこれ考え事しちゃって、お鍋吹きこぼれちゃったんだ。けどね、味はすごく美味しくできたよ。君がご近所さんだったら届けてあげたいくらい。この作業通話アプリがもっともっと進化したら。':
  uv run python scripts/test_qwen_tts_client.py --server {{ server }} --mode non-stream --ref-audio {{ ref_audio }} --ref-text {{ ref_text }}

test-qwen-tts-stream server='http://localhost:12393' ref_audio='5_vocals_cut.wav' ref_text='そうそう、この間気分転換に料理したんだ。テスト勉強のモチベを上げるためにも、自分の好物を作ることにしたんだ。あれこれ考え事しちゃって、お鍋吹きこぼれちゃったんだ。けどね、味はすごく美味しくできたよ。君がご近所さんだったら届けてあげたいくらい。この作業通話アプリがもっともっと進化したら。':
  uv run python scripts/test_qwen_tts_client.py --server {{ server }} --mode stream --ref-audio {{ ref_audio }} --ref-text {{ ref_text }}

test-qwen-tts-stream-play server='http://localhost:12393' ref_audio='5_vocals_cut.wav' ref_text='そうそう、この間気分転換に料理したんだ。テスト勉強のモチベを上げるためにも、自分の好物を作ることにしたんだ。あれこれ考え事しちゃって、お鍋吹きこぼれちゃったんだ。けどね、味はすごく美味しくできたよ。君がご近所さんだったら届けてあげたいくらい。この作業通話アプリがもっともっと進化したら。':
  uv run python scripts/test_qwen_tts_client.py --server {{ server }} --mode stream-play --ref-audio {{ ref_audio }} --ref-text {{ ref_text }}

# deploy

install-model:
  uv lock
  uv sync
  just install-nltk

  just install-funasr-model
  just install-whisper
  just install-sensevoice
  just install-bert-model
  just install-gsv-model
  just install-qwen-tts

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

install-sensevoice:
  uv lock
  uv sync
  # SenseVoiceSmall
  uv run modelscope download --model iic/SenseVoiceSmall --local_dir ./models/SenseVoiceSmall

install-bert-model:
  uv lock
  uv sync
  uv run modelscope download --model pengzhendong/chinese-hubert-base --local_dir ./models/chinese-hubert-base
  uv run modelscope download --model dienstag/chinese-roberta-wwm-ext-large --local_dir ./models/chinese-roberta-wwm-ext-large  \
  pytorch_model.bin added_tokens.json config.json configuration.json README.md special_tokens_map.json tokenizer_config.json tokenizer.json
  # 这里不能用 --exclude 同时排除 tf_model.h5 和 flax_model.msgpack，多次 exclude 只会保留最后一个，所以这里指定了所有需要的文件

install-gsv-model:
  uv lock
  uv sync
  uv run modelscope download --model xnnehang/elaina-gsv-v2 --local_dir ./models/gptsovits/elaina


install-qwen-tts:
  uv lock
  uv sync
  uv run modelscope download --model Qwen/Qwen3-TTS-12Hz-1.7B-Base --local_dir ./models/Qwen3-TTS-12Hz-1.7B-Base

# Code Quality Check

fmt: # 似乎不会检查被 .gitignore 忽略的文件
  uv run ruff check --fix --select I . --exclude packages --exclude .git --exclude justfile
  uv run ruff format . --exclude packages --exclude .git --exclude justfile

lint:
  uv run pyright src/lab tests memory_bench
  uv run ruff check . --exclude packages --exclude .git --exclude justfile

fmt-docs:
  prettier --ignore-path .prettierignore --write '**/*.md'

test:
  uv run pytest tests -vvv
  uv run pytest memory_bench/tests -vvv

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

# memory bench

memory-chat-server port='8080':
  uv run memory_bench/server/chat_server.py --port {{ port }} --enable-graph

memory-chat-cli base_url='http://localhost:8080' endpoint='/v1/chat/completions':
  uv run memory_bench/server/chat_cli.py --base-url {{ base_url }} --endpoint {{ endpoint }}

# 快速调试：使用 /memory/chat 端点（带 session 管理）
memory-chat-cli-memory base_url='http://localhost:8080':
  @echo "Starting chat CLI with /memory/chat endpoint..."
  uv run memory_bench/server/chat_cli.py --base-url {{ base_url }} --endpoint memory

# 快速调试：使用 /v1/chat/completions 端点（OpenAI 兼容）
memory-chat-cli-openai base_url='http://localhost:8080':
  @echo "Starting chat CLI with /v1/chat/completions endpoint..."
  uv run memory_bench/server/chat_cli.py --base-url {{ base_url }} --endpoint openai

build-index limit='' tail='' offset='':
  uv run memory_bench/scripts/build_index.py --force {{ if limit != '' { '--limit ' + limit } else { '' } }} {{ if tail != '' { '--tail ' + tail } else { '' } }} {{ if offset != '' { '--offset ' + offset } else { '' } }}

annotate-all:
  uv run memory_bench/scripts/annotate_all.py

compile-events:
  uv run memory_bench/scripts/compile_events.py

reset-mem0-graph:
  uv run memory_bench/scripts/mem0_to_graph.py reset \
    --state-db memory_bench/state/graphify/state.sqlite \
    --out-dir memory_bench/logs/replay_mem0/graphify \
    --reset-output

mem0-to-graph:
  latest_export=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/replay_mem0) && \
  uv run memory_bench/scripts/mem0_to_graph.py add \
    --input "$latest_export" \
    --out-dir memory_bench/logs/replay_mem0/graphify \
    --state-db memory_bench/state/graphify/state.sqlite \
    --prefix graph

mem0-graph-to-cypher:
  nodes=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/replay_mem0/graphify --glob "graph_nodes_*.jsonl") && \
  edges=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/replay_mem0/graphify --glob "graph_edges_*.jsonl") && \
  uv run memory_bench/scripts/graph_to_cypher.py \
    --nodes "$nodes" \
    --edges "$edges" \
    --out-dir memory_bench/logs/replay_mem0/graphify/neo4j \
    --prefix graph

clean-and-restart-neo4j:
  # 如果端口占用可以尝试调用
  rm -rf memory_bench/neo4j-data/
  sleep 3
  docker compose -f memory_bench/docker-compose.neo4j.yml down --remove-orphans
  rm -rf memory_bench/neo4j-data/mem0/data
  rm -rf memory_bench/neo4j-data/zep/data
  rm -rf memory_bench/neo4j-data/cognee/data
  docker compose -f memory_bench/docker-compose.neo4j.yml up -d

# =============================================================================
# Cleanup Recipes — 基础清理原语
# =============================================================================

clean-neo4j:
  # 清空 Neo4j 图数据（不重启容器，使用 Cypher DETACH DELETE）
  # 影响两条管线，共享同一个容器
  python memory_bench/scripts/neo4j_clear.py

clean-bench-logs:
  # 清理 bench logs（只影响离线管线的中间产物）
  rm -rf memory_bench/logs/

clean-bench-state:
  # 清理 bench state（checkpoint / state.sqlite，只影响离线管线）
  rm -rf memory_bench/state/

clean-bench-events:
  # 清理 bench events（离线管线中间产物）
  rm -rf memory_bench/data/events/

clean-bench-claims:
  # 清理 bench claims（离线管线中间产物）
  rm -rf memory_bench/data/claims/

# --- 实时管线清理 ---

clean-realtime:
  # 实时管线只依赖 Neo4j 和 mem0 的 qdrant storage
  # 清理 qdrant storage（mem0 本地持久化）+ Neo4j
  rm -rf memory_bench/state/qdrant_storage/
  just clean-neo4j

# --- 增量命令（去掉 --force，依赖脚本自身的增量检查）---

mem0-ingest:
  # 增量 ingest（依赖 checkpoint，不清理）
  uv run memory_bench/scripts/replay_mem0.py ingest

mem0-ingest-graph-store:
  # 增量 ingest，启用 mem0 原生 graph store（Neo4j）
  uv run memory_bench/scripts/replay_mem0.py ingest --graph-store neo4j

mem0-export:
  # 导出当前 mem0 快照
  uv run memory_bench/scripts/replay_mem0.py export

claimify-all:
  # 增量 claimify（依赖 by_conv/*.jsonl 存在则 skip）
  latest_export=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/replay_mem0 --glob "export_*.jsonl") && \
  uv run ./memory_bench/scripts/claimify_all.py --input "$latest_export" --workers 2

compile-claims:
  # 汇总 claims（增量，除非 --force）
  uv run ./memory_bench/scripts/compiled_claims.py

memory-item-to-cypher:
  just mem0-to-graph
  just mem0-graph-to-cypher

claim-items-to-cypher:
  uv run memory_bench/scripts/claims_to_graph.py add
  claim_nodes=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/claims/graphify --glob "claims_nodes_*.jsonl") && \
  claim_edges=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/claims/graphify --glob "claims_edges_*.jsonl") && \
  uv run memory_bench/scripts/graph_to_cypher.py \
    --nodes "$claim_nodes" \
    --edges "$claim_edges" \
    --out-dir memory_bench/logs/claims/graphify/neo4j \
    --prefix claims


export-neo4j-schema-docs:
  # 一次生成节点/关系 schema + 边 schema 文档（默认参数）
  uv run memory_bench/scripts/export_node_schema.py
  uv run memory_bench/scripts/export_edge_schema.py

neo4j-apply-cypher:
  # mem0 graph → mem0 容器
  constraints_file=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/replay_mem0/graphify/neo4j --glob "graph_constraints_*.cypher") && \
  import_file=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/replay_mem0/graphify/neo4j --glob "graph_import_*.cypher") && \
  uv run memory_bench/scripts/neo4j_apply_cypher.py mem0 \
    --constraints "$constraints_file" \
    --import-file "$import_file"
  # claims graph → mem0 容器
  claims_constraints=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/claims/graphify/neo4j --glob "claims_constraints_*.cypher") && \
  claims_import=$(uv run memory_bench/scripts/latest_file.py --export-dir memory_bench/logs/claims/graphify/neo4j --glob "claims_import_*.cypher") && \
  uv run memory_bench/scripts/neo4j_apply_cypher.py mem0 \
    --constraints "$claims_constraints" \
    --import-file "$claims_import"

mem0-rerun-add:
  just build-index
  just annotate-all
  just compile-events
  just mem0-ingest
  just mem0-export
  just claimify-all
  just compile-claims
  just memory-item-to-cypher
  just claim-items-to-cypher
  just neo4j-apply-cypher

mem0-rerun-graph-store:
  just build-index
  just annotate-all
  just compile-events
  just mem0-ingest-graph-store
  just mem0-export

mem0-run-from-graph-store:
  just clean-neo4j
  just clean-bench-state
  just clean-bench-claims
  just clean-bench-logs
  just mem0-rerun-graph-store

# =============================================================================
# 快速测试入口 — 从不同 LLM 调用点切入
# =============================================================================

mem0-run-from-annotate:
  # 从 annotate_all 开始（LLM #1：事件标注）
  # 清空所有 → 所有步骤都强制重跑
  just clean-neo4j
  just clean-bench-state
  just clean-bench-claims
  just clean-bench-events
  just clean-bench-logs
  just mem0-rerun-add

mem0-run-from-ingest:
  # 从 replay_mem0 ingest 开始（跳过 LLM #1 标注）
  # 保留 events → annotate-all 增量 skip
  # 清 state/claims/logs → ingest/export/claimify 全部重跑
  just clean-neo4j
  just clean-bench-state
  just clean-bench-claims
  just clean-bench-logs
  just mem0-rerun-add

mem0-run-from-claim:
  # 从 claimify_all 开始（LLM #3：claim 提取）
  # 保留 events + export → annotate/ingest/export 都增量 skip
  # 清 claims → claimify 及之后强制重跑
  just clean-neo4j
  just clean-bench-state
  just clean-bench-claims
  just mem0-rerun-add

mem0-run-real-time:
  # 实时管线：清理 + 启动 server
  just clean-realtime
  just memory-chat-server
