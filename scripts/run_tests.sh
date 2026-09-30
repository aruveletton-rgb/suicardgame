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

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
RUN_E2E="${RUN_PLAYWRIGHT_E2E:-0}"

if [[ "$RUN_E2E" != "0" && "$RUN_E2E" != "1" ]]; then
  echo "RUN_PLAYWRIGHT_E2E must be 0 or 1." >&2
  exit 2
fi
redact_output() {
  sed -E 's/((session_id|reconnect_token|player_id|token)=)[^&[:space:]"]+/\1REDACTED/gI'
}

cd "$ROOT"
export SUICARDGAME_DATA_DIR="$(mktemp -d)"

"$PYTHON_BIN" -m pytest -q backend/tests
"$PYTHON_BIN" scripts/validate-card-assets.py
npm --prefix "$ROOT/frontend" run build

cd "$ROOT/frontend"
npx playwright test --list

if [[ "$RUN_E2E" == "1" ]]; then
  npx playwright test --config=playwright.config.ts 2>&1 | redact_output
  npx playwright test --config=playwright.production.config.ts 2>&1 | redact_output
else
  echo "Playwright E2E skipped. Set RUN_PLAYWRIGHT_E2E=1 to run it."
fi
