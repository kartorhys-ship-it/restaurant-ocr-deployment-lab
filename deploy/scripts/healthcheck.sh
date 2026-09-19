#!/usr/bin/env bash
# Independent Healthcheck Probe for Receipt Platform
set -euo pipefail

TARGET_HOST="127.0.0.1"
TARGET_PORT="8000"
BASE_URL="http://${TARGET_HOST}:${TARGET_PORT}"

echo "==> Running Backend Liveness Probe: ${BASE_URL}/api/health/live"
LIVE_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${BASE_URL}/api/health/live" || echo "000")
if [ "$LIVE_CODE" != "200" ]; then
    echo "ERROR: Liveness check failed with HTTP ${LIVE_CODE}"
    exit 1
fi
echo "    -> Backend Liveness OK (HTTP 200)"

echo "==> Running Backend Readiness Probe: ${BASE_URL}/api/health/ready"
READY_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/api/health/ready" || echo "000")
if [ "$READY_CODE" != "200" ]; then
    echo "ERROR: Readiness check failed with HTTP ${READY_CODE}"
    exit 1
fi
echo "    -> Backend Readiness OK (HTTP 200)"

# Nginx Proxy Layer Probe (verifies Nginx edge routing when Nginx is active)
if command -v nginx >/dev/null 2>&1 && systemctl is-active --quiet nginx 2>/dev/null; then
    echo "==> Running Nginx Reverse Proxy Probe"
    NGINX_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -H "Host: receipts.restaurant-domain.internal" "http://127.0.0.1/api/health/live" || echo "000")
    if [ "$NGINX_CODE" != "301" ] && [ "$NGINX_CODE" != "200" ]; then
        echo "ERROR: Nginx proxy probe failed with HTTP ${NGINX_CODE}"
        exit 1
    fi
    echo "    -> Nginx Proxy OK (HTTP ${NGINX_CODE})"
fi

echo "SUCCESS: All healthcheck probes passed."
exit 0
