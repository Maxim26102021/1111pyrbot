#!/usr/bin/env bash
set -euo pipefail

uvicorn services.payments.app.api:app --host 0.0.0.0 --port 8080
