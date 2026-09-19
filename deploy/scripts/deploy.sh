#!/usr/bin/env bash
# 7-Step Zero-Downtime Atomic Deployment Script
set -euo pipefail

APP_ROOT="/srv/receipt-app"
RELEASES_DIR="${APP_ROOT}/releases"
CURRENT_LINK="${APP_ROOT}/current"
PREVIOUS_LINK="${APP_ROOT}/previous"
SHARED_DIR="${APP_ROOT}/shared"

RELEASE_TS=$(date +%Y%m%d_%H%M%S)
NEW_RELEASE_PATH="${RELEASES_DIR}/${RELEASE_TS}"

echo "=================================================="
echo "  Deploying Receipt Platform: Release ${RELEASE_TS}"
echo "=================================================="

# 1. Ensure directories exist
mkdir -p "${RELEASES_DIR}" "${SHARED_DIR}/logs" "${SHARED_DIR}/uploads-temp"

# 2. Stage isolated release directory
echo "==> Step 1 & 2: Staging new release at ${NEW_RELEASE_PATH}"
mkdir -p "${NEW_RELEASE_PATH}"
cp -a . "${NEW_RELEASE_PATH}/"

# Link shared environment and runtime assets
ln -sfn "${SHARED_DIR}/.env" "${NEW_RELEASE_PATH}/.env" 2>/dev/null || true

# 3. Retain previous pointer for atomic rollback
if [ -L "${CURRENT_LINK}" ] || [ -e "${CURRENT_LINK}" ]; then
    echo "==> Step 3: Retaining active target as previous pointer"
    OLD_TARGET=$(readlink -f "${CURRENT_LINK}")
    ln -sfn "${OLD_TARGET}" "${PREVIOUS_LINK}"
fi

# 4. Atomic cutover
echo "==> Step 4: Atomic symlink switch -> ${NEW_RELEASE_PATH}"
ln -sfn "${NEW_RELEASE_PATH}" "${CURRENT_LINK}"

# 5. Graceful daemon reload
echo "==> Step 5: Reloading application and proxy daemons"
sudo supervisorctl restart receipt-api receipt-worker
sudo nginx -t && sudo systemctl reload nginx

# 6. Post-deployment health verification
echo "==> Step 6: Post-deployment healthcheck probe"
if ! "${NEW_RELEASE_PATH}/deploy/scripts/healthcheck.sh"; then
    echo "CRITICAL: Healthcheck failed after cutover! Initiating rollback..."
    # 7. Automated rollback on failure
    "${NEW_RELEASE_PATH}/deploy/scripts/rollback.sh"
    exit 1
fi

echo "=================================================="
echo "  SUCCESS: Release ${RELEASE_TS} deployed and healthy!"
echo "=================================================="
exit 0
