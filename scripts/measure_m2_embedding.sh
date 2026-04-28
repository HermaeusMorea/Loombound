#!/usr/bin/env bash
# Measure how often the embedding cache intercepts M2 arc-classification
# calls during one gameplay session.
#
# Usage:
#   scripts/measure_m2_embedding.sh                       # pick latest saga
#   scripts/measure_m2_embedding.sh --saga <saga.json>    # specific saga
#   scripts/measure_m2_embedding.sh --no-embed            # baseline: disable embedder
#
# After you finish playing and exit the game, the script prints a
# breakdown of LLM calls vs. embedding cache hits within this session.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

REPO_ROOT="$(pwd)"
LLM_LOG="$REPO_ROOT/logs/llm.md"
DUMP_PATH="/tmp/m2.jsonl"

saga=""
disable_embed=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --saga)
            saga="$2"; shift 2 ;;
        --no-embed)
            disable_embed=1; shift ;;
        -h|--help)
            grep '^#' "$0" | sed -n '2,11p' | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)
            echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

# Auto-pick latest saga JSON if not specified
if [[ -z "$saga" ]]; then
    saga=$(ls -t data/sagas/*.json 2>/dev/null \
        | grep -v '_rules\.json$' \
        | grep -v '_narration_table\.json$' \
        | grep -v '_toll_lexicon\.json$' \
        | head -1)
    if [[ -z "$saga" ]]; then
        echo "No saga found under data/sagas/. Run ./loombound gen first." >&2
        exit 1
    fi
fi

if [[ ! -f "$saga" ]]; then
    echo "Saga file not found: $saga" >&2
    exit 1
fi

START="$(date -u '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo "saga:     $saga"
echo "start:    $START UTC"
echo "dump:     $DUMP_PATH"
if [[ "$disable_embed" == "1" ]]; then
    echo "mode:     baseline (embedder DISABLED)"
else
    echo "mode:     embedding enabled"
fi
echo "========================================"
echo "Play the saga. Exit (Ctrl-C or quit) when you have enough data points."
echo ""

rm -f "$DUMP_PATH"

env_prefix=(
    "HF_HUB_OFFLINE=1"
    "M2_DUMP_PATH=$DUMP_PATH"
)
if [[ "$disable_embed" == "1" ]]; then
    env_prefix+=("LOOMBOUND_EMBEDDER_DISABLED=1")
fi

env "${env_prefix[@]}" ./loombound run --saga "$saga" --lang zh || true

echo ""
echo "========================================"
echo "=== Session report ==="
echo "========================================"

# Analyse llm.md entries written after $START.
awk -v start="$START" '
  /^## \[[0-9-]+ [0-9:]+ UTC\]/ {
    match($0, /\[([0-9-]+ [0-9:]+)/, ts)
    if (ts[1] >= start) {
      if (/M2 ARC UPDATE RESPONSE/)      llm_calls++
      else if (/M2 EMBEDDING HIT/)        emb_hits++
    }
  }
  END {
    total = (llm_calls+0) + (emb_hits+0)
    printf "LLM 真调用 (Haiku):  %d\n", llm_calls+0
    printf "Embedding 命中:      %d\n", emb_hits+0
    printf "本局 M2 总触发:      %d\n", total
    if (total > 0) {
      printf "Embedding 命中率:    %.1f%%\n", 100 * (emb_hits+0) / total
    }
    # Haiku cached-hit pricing estimate
    saved_cost = (emb_hits+0) * 0.0012
    actual_cost = (llm_calls+0) * 0.0012
    printf "本局实际 M2 花费:    $%.4f\n", actual_cost
    printf "Embedding 省下:      $%.4f\n", saved_cost
  }
' "$LLM_LOG"

echo ""
dump_lines=$(wc -l < "$DUMP_PATH" 2>/dev/null || echo 0)
echo "Dump 行数 (交叉验证 LLM 真调用): $dump_lines"

echo ""
echo "=== 前 5 条 Embedding 命中（本局）==="
awk -v start="$START" '
  /^## \[[0-9-]+ [0-9:]+ UTC\]/ {
    match($0, /\[([0-9-]+ [0-9:]+)/, ts)
    if (ts[1] >= start && /M2 EMBEDDING HIT/) print
  }
' "$LLM_LOG" | head -5

echo ""
echo "dump 路径保留在 $DUMP_PATH (供后续 eval_m2_openai.py 回放对比)"
