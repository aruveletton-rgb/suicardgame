#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/start_backend.sh [--help]

Starts the backend for local or server-internal use.

Environment overrides:
  SUICARDGAME_HOST      Bind host (default: 127.0.0.1)
  SUICARDGAME_PORT      Bind port (default: 8012)
  SUICARDGAME_DATA_DIR  Private room data directory

This script does not configure public access, Nginx, or systemd.
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
cd "$ROOT"

HOST="${SUICARDGAME_HOST:-127.0.0.1}"
PORT="${SUICARDGAME_PORT:-8012}"
DATA_DIR="${SUICARDGAME_DATA_DIR:-$ROOT/runtime/data/rooms}"

mkdir -p -- "$DATA_DIR"
chmod 700 -- "$DATA_DIR"

if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" ]]; then
  echo "WARNING: non-local bind requested explicitly: $HOST" >&2
fi

echo "Starting suicardgame backend on ${HOST}:${PORT}. Access logging is disabled to protect credentials."
exec python -m uvicorn backend.app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --no-access-log
