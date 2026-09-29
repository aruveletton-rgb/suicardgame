#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/smoke_backend.sh [--help]

Starts a temporary backend on 127.0.0.1:8012, checks /api/v1/health, then
terminates only the process started by this script and verifies port release.

Environment override:
  SUICARDGAME_SMOKE_PORT  Local smoke port (default: 8012)
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") ;;
  *) usage >&2; exit 2 ;;
esac

ROOT="/home/suicardgame"
CONDA_SH="/home/miniconda3/etc/profile.d/conda.sh"
HOST="127.0.0.1"
PORT="${SUICARDGAME_SMOKE_PORT:-8012}"
SMOKE_DIR=""
SMOKE_PID=""

port_is_listening() {
  ss -H -ltn 2>/dev/null | awk -v suffix=":${PORT}" '$4 ~ suffix "$" {found=1} END {exit found ? 0 : 1}'
}

cleanup() {
  local exit_status=$?
  local private_dir="$SMOKE_DIR"

  if [[ -n "$SMOKE_PID" ]] && kill -0 "$SMOKE_PID" 2>/dev/null; then
    kill -TERM "$SMOKE_PID" 2>/dev/null || true
    wait "$SMOKE_PID" 2>/dev/null || true
  fi
  SMOKE_PID=""

  if [[ -n "$private_dir" && -d "$private_dir" && ! -L "$private_dir" && "$private_dir" == /tmp/suicardgame-smoke.* ]]; then
    find "$private_dir" -depth -delete
  fi
  SMOKE_DIR=""
  return "$exit_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -f "$CONDA_SH" ]]; then
  echo "Conda activation script not found: $CONDA_SH" >&2
  exit 1
fi
if port_is_listening; then
  echo "Port $PORT is already in use; smoke was not started." >&2
  exit 1
fi

source "$CONDA_SH"
conda activate audio
cd "$ROOT"
unset TEST_MODE || true

SMOKE_DIR="$(mktemp -d /tmp/suicardgame-smoke.XXXXXX)"
SMOKE_LOG="$SMOKE_DIR/server.log"

SUICARDGAME_DATA_DIR="$SMOKE_DIR/rooms" \
  python -m uvicorn backend.app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --no-access-log \
    >"$SMOKE_LOG" 2>&1 &
SMOKE_PID=$!

ready=0
for _ in $(seq 1 15); do
  if curl -fsS "http://${HOST}:${PORT}/api/v1/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  echo "Backend smoke health endpoint did not become ready." >&2
  exit 1
fi

curl -fsS "http://${HOST}:${PORT}/api/v1/health"
echo

cleanup
trap - EXIT INT TERM

if port_is_listening; then
  echo "Port $PORT is still listening after smoke cleanup." >&2
  exit 1
fi

echo "Backend smoke passed and port $PORT was released."
