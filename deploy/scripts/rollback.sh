#!/usr/bin/env bash
# Automated Reversible System Rollback Script
# Reverts /srv/receipt-app/current/ symlink to previous release in /srv/receipt-app/releases/
set -euo pipefail

APP_ROOT="/srv/receipt-app"
CURRENT_LINK="${APP_ROOT}/current"
PREVIOUS_LINK="${APP_ROOT}/previous"

echo "=================================================="
echo "  INITIATING EMERGENCY ROLLBACK"
echo "=================================================="

if [ ! -L "${PREVIOUS_LINK}" ] && [ ! -e "${PREVIOUS_LINK}" ]; then
    echo "FATAL: No previous release link found at ${PREVIOUS_LINK}. Rollback impossible."
    exit 1
fi

PREV_TARGET=$(readlink -f "${PREVIOUS_LINK}")
echo "==> Reverting 'current' pointer to previous release: ${PREV_TARGET}"
ln -sfn "${PREV_TARGET}" "${CURRENT_LINK}"

echo "==> Reloading daemons on previous release"
sudo supervisorctl restart receipt-api receipt-worker
sudo nginx -t && sudo systemctl reload nginx

echo "==> Validating rollback state health"
if "${CURRENT_LINK}/deploy/scripts/healthcheck.sh"; then
    echo "SUCCESS: Rollback complete. System restored to healthy state."
    exit 0
else
    echo "CRITICAL: System remains degraded even after rollback!"
    exit 2
fi
