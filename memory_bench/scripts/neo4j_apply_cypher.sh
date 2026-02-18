#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME=$(basename "$0")
DEFAULT_GRAPHIFY_OUT_DIR="${GRAPHIFY_OUT_DIR:-memory_bench/logs/replay_mem0/graphify}"

usage() {
  cat <<USAGE
Usage:
  ${SCRIPT_NAME} <target> <cypher_dir> <prefix>
  ${SCRIPT_NAME} <target> <prefix>

Examples:
  ${SCRIPT_NAME} mem0 memory_bench/logs/replay_mem0/graphify/neo4j graph
  ${SCRIPT_NAME} zep  memory_bench/logs/replay_zep/graphify/neo4j graph
  ${SCRIPT_NAME} cognee graph

Arguments:
  target      Neo4j target instance: mem0 | zep | cognee
  cypher_dir  Directory containing <prefix>_constraints.cypher and <prefix>_import.cypher
              (optional, default: <GRAPHIFY_OUT_DIR>/neo4j)
  prefix      Cypher file prefix

Environment:
  GRAPHIFY_OUT_DIR  Base out dir used by graphify_pipeline (default: ${DEFAULT_GRAPHIFY_OUT_DIR})
USAGE
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
  exit 2
fi

TARGET="$1"
if [[ $# -eq 2 ]]; then
  CYPHER_DIR="${DEFAULT_GRAPHIFY_OUT_DIR}/neo4j"
  PREFIX="$2"
else
  CYPHER_DIR="$2"
  PREFIX="$3"
fi

case "${TARGET}" in
  mem0)
    CONTAINER_NAME="membench-neo4j-mem0"
    DB_NAME="mem0"
    BROWSER_URL="http://localhost:7474"
    ;;
  zep)
    CONTAINER_NAME="membench-neo4j-zep"
    DB_NAME="zep"
    BROWSER_URL="http://localhost:7475"
    ;;
  cognee)
    CONTAINER_NAME="membench-neo4j-cognee"
    DB_NAME="cognee"
    BROWSER_URL="http://localhost:7476"
    ;;
  *)
    echo "[ERROR] Invalid target '${TARGET}'. Expected one of: mem0, zep, cognee." >&2
    usage
    exit 2
    ;;
esac

CONSTRAINTS_FILE="${CYPHER_DIR}/${PREFIX}_constraints.cypher"
IMPORT_FILE="${CYPHER_DIR}/${PREFIX}_import.cypher"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker command not found. Please install Docker first." >&2
  exit 127
fi

if [[ ! -f "${CONSTRAINTS_FILE}" ]]; then
  echo "[ERROR] Constraints file not found: ${CONSTRAINTS_FILE}" >&2
  exit 3
fi

if [[ ! -f "${IMPORT_FILE}" ]]; then
  echo "[ERROR] Import file not found: ${IMPORT_FILE}" >&2
  exit 3
fi

if ! docker ps --format '{{.Names}}' | rg -x "${CONTAINER_NAME}" >/dev/null 2>&1; then
  echo "[ERROR] Container '${CONTAINER_NAME}' is not running." >&2
  echo "        Start it first: docker compose -f memory_bench/docker-compose.neo4j.yml up -d neo4j_${TARGET}" >&2
  exit 4
fi

run_cypher_file() {
  local file_path="$1"
  local phase="$2"

  echo "[INFO] (${phase}) Applying: ${file_path}"
  if docker exec -i "${CONTAINER_NAME}" \
    cypher-shell -u neo4j -p neo4jneo4j -d "${DB_NAME}" < "${file_path}"; then
    echo "[INFO] (${phase}) Success: ${file_path}"
  else
    local exit_code=$?
    echo "[ERROR] (${phase}) Failed: ${file_path} (exit=${exit_code})" >&2
    return "${exit_code}"
  fi
}

echo "[INFO] Target      : ${TARGET}"
echo "[INFO] Container   : ${CONTAINER_NAME}"
echo "[INFO] Database    : ${DB_NAME}"
echo "[INFO] Cypher dir  : ${CYPHER_DIR}"
echo "[INFO] Prefix      : ${PREFIX}"

echo "[INFO] Step 1/2: apply constraints"
run_cypher_file "${CONSTRAINTS_FILE}" "constraints"

echo "[INFO] Step 2/2: apply import"
run_cypher_file "${IMPORT_FILE}" "import"

echo "[INFO] All done. Open Neo4j Browser: ${BROWSER_URL}"
