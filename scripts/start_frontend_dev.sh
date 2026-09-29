#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/start_frontend_dev.sh [--help]

Starts the Vite development server on localhost. This is not a production
deployment command.

Environment overrides:
  SUICARDGAME_FRONTEND_HOST  Bind host (default: 127.0.0.1)
  SUICARDGAME_FRONTEND_PORT  Bind port (default: 5173)
  VITE_BACKEND_TARGET        Backend proxy target (default from Vite config)
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

HOST="${SUICARDGAME_FRONTEND_HOST:-127.0.0.1}"
PORT="${SUICARDGAME_FRONTEND_PORT:-5173}"

echo "Starting Vite development server on ${HOST}:${PORT}; this is not production deployment."
exec npm run dev -- --host "$HOST" --port "$PORT"
