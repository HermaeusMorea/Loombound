#!/usr/bin/env bash
# Loombound campaign generator
#
# Usage:
#   ./gen.sh "新加坡地下黑客社区与企业监控" --nodes 6 --lang zh
#   ./gen.sh "lighthouse keeper's descent" --nodes 6
#   ./gen.sh "drowned district" --model deepseek --nodes 8
#   ./gen.sh "canal cult" --model anthropic:claude-haiku-4-5
#   ./gen.sh "太阳帆时代考古调查" --tone "忧郁但不绝望的太空考古悬疑"
#   ./gen.sh "债务猎人逃亡" --worldview "木星轨道殖民地由债务公会控制"
#   ./gen.sh --help
#
# Shorthand flags:
#   --model PROVIDER[:MODEL]  → --provider PROVIDER [--provider-model MODEL]
#
# All other flags are passed through to generate_campaign.py unchanged.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".env" ]]; then
    set -a
    source .env
    set +a
fi

# ---------------------------------------------------------------------------
# Parse shorthand flags
# ---------------------------------------------------------------------------

provider=""
provider_model=""
passthrough=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            val="$2"; shift 2
            if [[ "$val" == *:* ]]; then
                provider="${val%%:*}"
                provider_model="${val#*:}"
            else
                provider="$val"
            fi
            ;;
        *)
            passthrough+=("$1"); shift
            ;;
    esac
done

# Build generate_campaign.py argument list
py_args=("${passthrough[@]+"${passthrough[@]}"}")

[[ -n "$provider" ]] && py_args+=(--provider "$provider")
[[ -n "$provider_model" ]] && py_args+=(--provider-model "$provider_model")

exec "$SCRIPT_DIR/.venv/bin/python" generate_campaign.py "${py_args[@]+"${py_args[@]}"}"
