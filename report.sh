#!/usr/bin/env bash
# Loombound LLM usage report helper
#
# Usage:
#   ./report.sh
#   ./report.sh --campaign wall_street_dark_secrets
#   ./report.sh --log logs/llm.md
#
# All flags are passed through to report_llm_usage.py unchanged.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

exec "$SCRIPT_DIR/.venv/bin/python" report_llm_usage.py "${@+"$@"}"
