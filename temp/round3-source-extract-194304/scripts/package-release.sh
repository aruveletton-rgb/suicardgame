#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

"$PYTHON_BIN" "$ROOT/scripts/generate-card-assets.py"
"$PYTHON_BIN" "$ROOT/scripts/validate-card-assets.py"
"$PYTHON_BIN" -m pytest -q "$ROOT/backend/tests"
npm --prefix "$ROOT/frontend" run build
"$PYTHON_BIN" "$ROOT/scripts/package_release.py"
