#!/usr/bin/env bash
set -euo pipefail

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$EXPERIMENT_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DATASET="${DATASET:?Set DATASET to an external labelled JSON file}"
KNOWLEDGE_BASE="${KNOWLEDGE_BASE:-$PROJECT_ROOT/aag/knowledge_base}"
RUN_ROOT="${RUN_ROOT:-$EXPERIMENT_DIR/runs/single-pass}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-ai/DeepSeek-V3}"
GPT_MODEL="${GPT_MODEL:-gpt-4o-mini}"
RUN_SCOPE="${RUN_SCOPE:-all}"

: "${DEEPSEEK_API_KEY:?Set DEEPSEEK_API_KEY in the environment}"
: "${GPT_API_KEY:?Set GPT_API_KEY in the environment}"

mkdir -p "$RUN_ROOT"

run_one() {
  local knowledge="$1"
  local planner="$2"
  local model="$3"
  local api_key="$4"
  local model_dir="$5"
  local output_dir="$RUN_ROOT/$model_dir/$knowledge-$planner"
  local knowledge_args=(--knowledge "$knowledge")

  if [[ "$knowledge" == "flat" ]]; then
    knowledge_args+=(--flat-mode direct --direct-doc-max-chars 900)
  fi

  echo "START model=$model planner=$planner knowledge=$knowledge"
  OPENAI_API_KEY="$api_key" OPENAI_BASE_URL="$OPENAI_BASE_URL" \
    "$PYTHON_BIN" "$EXPERIMENT_DIR/evaluate.py" \
      "${knowledge_args[@]}" \
      --planner "$planner" \
      --model "$model" \
      --dataset "$DATASET" \
      --knowledge-base "$KNOWLEDGE_BASE" \
      --output-dir "$output_dir"
  echo "DONE model=$model planner=$planner knowledge=$knowledge"
}

run_model() {
  local model="$1"
  local api_key="$2"
  local model_dir="$3"

  run_one flat react "$model" "$api_key" "$model_dir"
  run_one flat llmcompiler "$model" "$api_key" "$model_dir"
  if [[ "$RUN_SCOPE" == "all" ]]; then
    run_one hierarchical react "$model" "$api_key" "$model_dir"
    run_one hierarchical llmcompiler "$model" "$api_key" "$model_dir"
  fi
}

if [[ "$RUN_SCOPE" != "all" && "$RUN_SCOPE" != "flat" ]]; then
  echo "RUN_SCOPE must be 'all' or 'flat'" >&2
  exit 2
fi

run_model "$DEEPSEEK_MODEL" "$DEEPSEEK_API_KEY" deepseek-v3
run_model "$GPT_MODEL" "$GPT_API_KEY" gpt-4o-mini
"$PYTHON_BIN" "$EXPERIMENT_DIR/summarize.py" "$RUN_ROOT"
