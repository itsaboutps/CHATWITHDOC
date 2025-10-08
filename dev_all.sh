#!/usr/bin/env bash
# Unified dev launcher for backend (FastAPI) + frontend (Next.js)
# Usage:
#   ./dev_all.sh            # start backend on 8000 (or BACKEND_PORT) and frontend on 3000
#   BACKEND_PORT=8010 ./dev_all.sh
#   ./dev_all.sh check      # print resolved config and exit

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  fi
fi
VENV_DIR="${VENV_DIR:-.venv}"

if [[ "${1:-}" == "check" ]]; then
  echo "Configuration:" && echo "  BACKEND_PORT=$BACKEND_PORT" && echo "  BACKEND_HOST=$BACKEND_HOST" && echo "  FRONTEND_PORT=$FRONTEND_PORT" && echo "  VENV_DIR=$VENV_DIR" && exit 0
fi

echo "[dev_all] Preparing Python virtual environment ($VENV_DIR)";
if [[ -d "$VENV_DIR" && ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "[dev_all] Detected malformed venv (missing activate). Recreating..." >&2
  mv "$VENV_DIR" "${VENV_DIR}.corrupt.$(date +%s)" || rm -rf "$VENV_DIR" || true
fi
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR" || { echo "[dev_all] First venv attempt failed; retrying with 'python'"; python -m venv "$VENV_DIR"; }
fi
if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "[dev_all] ERROR: activate script still missing after recreation. Aborting." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
VENV_PY="$VENV_DIR/bin/python"

echo "[dev_all] Installing backend dependencies (idempotent)"
"$VENV_PY" -m pip install -q --upgrade pip
"$VENV_PY" -m pip install -q -r backend/requirements.txt

if ! "$VENV_PY" -m pip show uvicorn >/dev/null 2>&1; then
  echo "[dev_all] ERROR: uvicorn not found in environment after install." >&2
  exit 2
fi

export USE_IN_MEMORY=${USE_IN_MEMORY:-true}
export NEXT_PUBLIC_BACKEND_URL="http://$BACKEND_HOST:$BACKEND_PORT"

kill_if_running() {
  local port=$1
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[dev_all] Port $port in use; attempting to free it (macOS/Linux only)."
    local pid
    pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t | head -n1 || true)
    if [[ -n "$pid" ]]; then
      echo "[dev_all] Killing existing process PID $pid on port $port"
      kill "$pid" || true
      sleep 1
    fi
  fi
}

kill_if_running "$BACKEND_PORT"

echo "[dev_all] Starting backend on $BACKEND_HOST:$BACKEND_PORT"
(
  cd backend
  uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload &
  BACKEND_PID=$!
  echo $BACKEND_PID > "$SCRIPT_DIR/.backend.pid"
  echo "[dev_all] Backend PID $BACKEND_PID"
)

echo "[dev_all] Preparing frontend (Next.js)"
(
  cd frontend
  if [[ ! -f .env.local ]]; then
    echo "NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL" > .env.local
  fi
  if [[ ! -d node_modules ]]; then
    echo "[dev_all] Installing npm dependencies"
    npm install --silent
  fi
  echo "[dev_all] Starting frontend on http://localhost:$FRONTEND_PORT (proxying to $NEXT_PUBLIC_BACKEND_URL)"
  # Run dev (foreground) – when you Ctrl+C, cleanup happens.
  PORT="$FRONTEND_PORT" npm run dev
)

echo "[dev_all] Shutting down..."
if [[ -f .backend.pid ]]; then
  PID=$(cat .backend.pid || true)
  if [[ -n "${PID}" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "[dev_all] Killing backend PID $PID"
    kill "$PID" || true
  fi
  rm -f .backend.pid
fi

echo "[dev_all] Done"
