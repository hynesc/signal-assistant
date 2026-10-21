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
PID_FILE="$SCRIPT_DIR/.bot.pid"

# Stop only the process started by this checkout.
if [[ -f "$PID_FILE" ]]; then
    bot_pid="$(cat "$PID_FILE")"
    if [[ "$bot_pid" =~ ^[0-9]+$ ]] && ps -p "$bot_pid" -o args= | grep -Fq -- "$SCRIPT_DIR/run_bot.py"; then
        kill "$bot_pid"
        for attempt in {1..50}; do
            if ! kill -0 "$bot_pid" 2>/dev/null; then break; fi
            sleep 0.1
        done
        if kill -0 "$bot_pid" 2>/dev/null; then
            echo "Bot has not stopped; leaving container and account data alone."
            exit 1
        fi
    fi
    rm -f "$PID_FILE"
fi
if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    docker stop "$CONTAINER_NAME" >/dev/null
fi

"$SCRIPT_DIR/.venv/bin/python" -m signal_bot.maintenance_cli \
    --signal-root "$SCRIPT_DIR/signal-data" --purge-runtime-data
rm -f "$SCRIPT_DIR/bot.log"
echo "Assistant stopped. Cleanup attempted; review any db_failed output."
