#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$APP_DIR/temp/log_filter_app.pid"
LOG_FILE="$APP_DIR/runtime_logs/log_filter_app_background.log"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
APP_FILE="$APP_DIR/app.py"
HOST="${LOG_FILTER_HOST:-0.0.0.0}"
PORT="${LOG_FILTER_PORT:-8052}"

is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_app() {
  mkdir -p "$APP_DIR/temp" "$APP_DIR/runtime_logs"

  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Error: virtualenv python not found: $PYTHON_BIN"
    exit 1
  fi

  if [[ ! -f "$APP_FILE" ]]; then
    echo "Error: app.py not found: $APP_FILE"
    exit 1
  fi

  if [[ -f "$PID_FILE" ]]; then
    local old_pid
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if is_running "$old_pid"; then
      echo "Already running. PID: $old_pid"
      echo "URL: http://$HOST:$PORT"
      exit 0
    fi
    rm -f "$PID_FILE"
  fi

  cd "$APP_DIR"
  nohup "$PYTHON_BIN" "$APP_FILE" --host "$HOST" --port "$PORT" >>"$LOG_FILE" 2>&1 &
  local pid="$!"
  echo "$pid" > "$PID_FILE"

  sleep 1
  if is_running "$pid"; then
    echo "Started. PID: $pid"
    echo "URL: http://$HOST:$PORT"
    echo "Log: $LOG_FILE"
  else
    rm -f "$PID_FILE"
    echo "Failed to start. Check log: $LOG_FILE"
    exit 1
  fi
}

stop_app() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "Not running: PID file not found."
    exit 0
  fi

  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if ! is_running "$pid"; then
    rm -f "$PID_FILE"
    echo "Not running: stale PID file removed."
    exit 0
  fi

  kill "$pid"
  for _ in {1..20}; do
    if ! is_running "$pid"; then
      rm -f "$PID_FILE"
      echo "Stopped. PID: $pid"
      exit 0
    fi
    sleep 0.2
  done

  kill -TERM "$pid" 2>/dev/null || true
  sleep 1
  if is_running "$pid"; then
    echo "Failed to stop PID $pid. You may need to kill it manually."
    exit 1
  fi

  rm -f "$PID_FILE"
  echo "Stopped. PID: $pid"
}

case "${1:-}" in
  --start)
    start_app
    ;;
  --stop)
    stop_app
    ;;
  *)
    echo "Usage: $0 --start | --stop"
    exit 2
    ;;
esac
