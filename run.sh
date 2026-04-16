#!/usr/bin/env bash
# Loombound launcher
#
# Usage:
#   ./run.sh                                  # authored content only
#   ./run.sh --slow deepseek                  # LLM mode, DeepSeek Slow Core
#   ./run.sh --slow deepseek --lang zh        # Chinese content
#   ./run.sh --slow deepseek --nodes 3        # limit to 3 nodes
#   ./run.sh --slow anthropic:claude-haiku-4-5 --fast gemma3:4b
#   ./run.sh --fast gemma4:e2b                # change Fast Core model only
#   ./run.sh --campaign data/campaigns/my.json --slow deepseek
#
# Shorthand flags (translated to play_cli args):
#   --slow PROVIDER[:MODEL]   → --llm --slow-provider PROVIDER [--slow-model MODEL]
#   --fast MODEL              → --fast MODEL (ollama model for text expansion)
#
# All other flags are passed through unchanged.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# ---------------------------------------------------------------------------
# Parse shorthand flags
# ---------------------------------------------------------------------------

slow_provider=""
slow_model=""
fast_model=""
passthrough=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --slow)
            val="$2"; shift 2
            if [[ "$val" == *:* ]]; then
                slow_provider="${val%%:*}"
                slow_model="${val#*:}"
            else
                slow_provider="$val"
            fi
            ;;
        --fast)
            fast_model="$2"; shift 2
            ;;
        *)
            passthrough+=("$1"); shift
            ;;
    esac
done

# Build play_cli argument list
py_args=("${passthrough[@]+"${passthrough[@]}"}")

if [[ -n "$slow_provider" ]]; then
    py_args+=(--llm --slow-provider "$slow_provider")
    [[ -n "$slow_model" ]] && py_args+=(--slow-model "$slow_model")
fi

[[ -n "$fast_model" ]] && py_args+=(--fast "$fast_model")

exec "$SCRIPT_DIR/.venv/bin/python" -m src.core.runtime.play_cli "${py_args[@]+"${py_args[@]}"}"
