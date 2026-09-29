#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/build_frontend.sh [--help]

Builds the frontend production assets with conservative CPU and memory limits.
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") ;;
  *) usage >&2; exit 2 ;;
esac

ROOT="/home/suicardgame"
CONDA_SH="/home/miniconda3/etc/profile.d/conda.sh"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Conda activation script not found: $CONDA_SH" >&2
  exit 1
fi

source "$CONDA_SH"
conda activate audio
cd "$ROOT/frontend"

export npm_config_jobs="${npm_config_jobs:-1}"
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=768}"

nice -n 10 ionice -c2 -n7 npm run build
