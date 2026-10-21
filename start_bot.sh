#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

CONTAINER_NAME="${SIGNAL_CONTAINER_NAME:-signal-assistant-api}"
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
BOT_SCRIPT="$SCRIPT_DIR/run_bot.py"
PID_FILE="$SCRIPT_DIR/.bot.pid"

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Create .venv and run .venv/bin/pip install -e . first."
    exit 1
fi
if [[ -z "${BOT_NUMBER:-}" || -z "${BOT_UUID:-}" || -z "${ADMIN_NUMBERS:-}" ]]; then
    echo "Set BOT_NUMBER, BOT_UUID, and ADMIN_NUMBERS in .env first."
    exit 1
fi
if [[ -f "$PID_FILE" ]]; then
    bot_pid="$(cat "$PID_FILE")"
    if [[ "$bot_pid" =~ ^[0-9]+$ ]] && ps -p "$bot_pid" -o args= | grep -Fq -- "$BOT_SCRIPT"; then
        echo "Assistant is already running (PID $bot_pid)."
        exit 0
    fi
    rm -f "$PID_FILE"
fi

mkdir -p signal-data
if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    docker start "$CONTAINER_NAME" >/dev/null
else
    docker run -d --name "$CONTAINER_NAME" \
        -p 127.0.0.1:8080:8080 \
        -v "$SCRIPT_DIR/signal-data:/home/.local/share/signal-cli" \
        -e MODE=normal -e LOG_LEVEL=warn \
        bbernhard/signal-cli-rest-api:latest >/dev/null
fi

api_ready=0
for attempt in {1..60}; do
    if curl -fsS -o /dev/null http://localhost:8080/v1/about 2>/dev/null; then
        api_ready=1
        break
    fi
    sleep 1
done
if [[ "$api_ready" -ne 1 ]]; then
    echo "Signal API did not become ready. Check docker logs for $CONTAINER_NAME."
    exit 1
fi

"$PYTHON_BIN" "$BOT_SCRIPT" --check-account-ready
nohup "$PYTHON_BIN" -u "$BOT_SCRIPT" > "$SCRIPT_DIR/bot.log" 2>&1 < /dev/null &
echo "$!" > "$PID_FILE"
echo "Assistant started (PID $(cat "$PID_FILE")). Logs: bot.log"
