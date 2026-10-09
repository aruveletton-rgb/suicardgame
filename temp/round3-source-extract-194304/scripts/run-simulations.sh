#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
"$PYTHON_BIN" -m pytest -q "$ROOT/backend/tests/test_room_lifecycle.py"
echo "Full 1000-game bot simulation is not implemented yet; see docs/TEST_REPORT.md."

