#!/usr/bin/env bash
# Independent Healthcheck Probe for Receipt Platform
set -euo pipefail

TARGET_HOST="127.0.0.1"
TARGET_PORT="8000"
BASE_URL="http://${TARGET_HOST}:${TARGET_PORT}"

echo "==> Running Liveness Probe: ${BASE_URL}/api/health/live"
LIVE_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${BASE_URL}/api/health/live" || echo "000")
if [ "$LIVE_CODE" != "200" ]; then
    echo "ERROR: Liveness check failed with HTTP ${LIVE_CODE}"
    exit 1
fi
echo "    -> Liveness OK (HTTP 200)"

echo "==> Running Readiness Probe: ${BASE_URL}/api/health/ready"
READY_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/api/health/ready" || echo "000")
if [ "$READY_CODE" != "200" ]; then
    echo "ERROR: Readiness check failed with HTTP ${READY_CODE}"
    exit 1
fi
echo "    -> Readiness OK (HTTP 200)"

echo "SUCCESS: All healthcheck probes passed."
exit 0
