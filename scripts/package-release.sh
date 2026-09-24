#!/usr/bin/env bash
set -euo pipefail

python scripts/generate-card-assets.py
python scripts/validate-card-assets.py
python -m pytest -q backend/tests
npm --prefix frontend run build
python scripts/package_release.py
