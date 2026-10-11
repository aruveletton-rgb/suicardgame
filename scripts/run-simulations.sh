#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
"$PYTHON_BIN" -m pytest -q "$ROOT/backend/tests/test_room_lifecycle.py"
"$PYTHON_BIN" "$ROOT/scripts/bot_simulation.py" --games "${BOT_SIMULATION_GAMES:-100}"

