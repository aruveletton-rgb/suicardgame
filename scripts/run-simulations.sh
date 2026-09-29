#!/usr/bin/env bash
set -euo pipefail
python -m pytest -q backend/tests/test_room_lifecycle.py
echo "Full 1000-game bot simulation is not implemented yet; see docs/TEST_REPORT.md."

