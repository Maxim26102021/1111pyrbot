#!/usr/bin/env bash
set -euo pipefail

: "${QUEUE_SUMMARIZE:=summarize}"
: "${QUEUE_SUMMARIZE_PRIORITY:=summarize_priority}"

uvicorn services.summarizer.app.api:app --host 0.0.0.0 --port 8000 &
UVICORN_PID=$!

celery -A services.summarizer.app.celery_app.celery_app worker \
  -Q "${QUEUE_SUMMARIZE},${QUEUE_SUMMARIZE_PRIORITY}" \
  -O fair \
  --concurrency=2 &
CELERY_PID=$!

terminate() {
  kill "$UVICORN_PID" "$CELERY_PID" 2>/dev/null || true
}

trap 'terminate' TERM INT

wait -n "$UVICORN_PID" "$CELERY_PID"
EXIT_CODE=$?

terminate
wait "$UVICORN_PID" "$CELERY_PID" 2>/dev/null || true

exit $EXIT_CODE
