#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/run_tests.sh [--help]

Runs backend tests, asset validation, frontend build, and Playwright test
discovery. Set RUN_PLAYWRIGHT_E2E=1 to also run the browser E2E suite.

No dependencies are installed by this script.
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") ;;
  *) usage >&2; exit 2 ;;
esac

ROOT="/home/suicardgame"
CONDA_SH="/home/miniconda3/etc/profile.d/conda.sh"
RUN_E2E="${RUN_PLAYWRIGHT_E2E:-0}"

if [[ "$RUN_E2E" != "0" && "$RUN_E2E" != "1" ]]; then
  echo "RUN_PLAYWRIGHT_E2E must be 0 or 1." >&2
  exit 2
fi
if [[ ! -f "$CONDA_SH" ]]; then
  echo "Conda activation script not found: $CONDA_SH" >&2
  exit 1
fi

redact_output() {
  sed -E 's/((session_id|reconnect_token|player_id|token)=)[^&[:space:]"]+/\1REDACTED/gI'
}

source "$CONDA_SH"
conda activate audio
cd "$ROOT"

nice -n 10 ionice -c2 -n7 python -m pytest -q backend/tests
python scripts/validate-card-assets.py
"$ROOT/scripts/build_frontend.sh"

cd "$ROOT/frontend"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$ROOT/.cache/ms-playwright}"
npx playwright test --list

if [[ "$RUN_E2E" == "1" ]]; then
  nice -n 10 ionice -c2 -n7 npx playwright test 2>&1 | redact_output
else
  echo "Playwright E2E skipped. Set RUN_PLAYWRIGHT_E2E=1 to run it."
fi
