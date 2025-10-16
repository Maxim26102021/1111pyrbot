#!/usr/bin/env bash
set -euo pipefail

celery -A services.scheduler.app.celery_app beat --pidfile= -l "${LOG_LEVEL:-INFO}" &
BEAT_PID=$!

celery -A services.scheduler.app.celery_app worker \
  -Q "${QUEUE_DIGEST:-digest}" \
  -O fair \
  --concurrency=1 \
  -l "${LOG_LEVEL:-INFO}" &
WORKER_PID=$!

terminate() {
  kill "$BEAT_PID" "$WORKER_PID" 2>/dev/null || true
}

trap terminate TERM INT

wait -n "$BEAT_PID" "$WORKER_PID"
EXIT_CODE=$?
terminate
wait "$BEAT_PID" "$WORKER_PID" 2>/dev/null || true
exit $EXIT_CODE
