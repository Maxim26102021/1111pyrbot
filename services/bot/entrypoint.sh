#!/usr/bin/env bash
set -euo pipefail

python -m services.bot.app.bot &
BOT_PID=$!

celery -A services.bot.app.celery_app.celery_app worker \
  -Q "${QUEUE_BOT:-bot}" \
  -O fair \
  --concurrency=2 \
  -l "${LOG_LEVEL:-INFO}" &
CELERY_PID=$!

terminate() {
  kill "$BOT_PID" "$CELERY_PID" 2>/dev/null || true
}

trap terminate TERM INT

wait -n "$BOT_PID" "$CELERY_PID"
EXIT_CODE=$?
terminate
wait "$BOT_PID" "$CELERY_PID" 2>/dev/null || true
exit $EXIT_CODE
