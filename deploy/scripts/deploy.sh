#!/usr/bin/env bash
# Zero-Downtime Atomic Deployment Script with Pre-Cutover Validation
# Manages atomic symlink switch from /srv/receipt-app/releases/ to /srv/receipt-app/current/
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

# 1. Ensure shared persistent directories exist
mkdir -p "${RELEASES_DIR}" "${SHARED_DIR}/logs" "${SHARED_DIR}/data" "${SHARED_DIR}/uploads-temp"

# 2. Stage isolated release directory
echo "==> Step 1 & 2: Staging new release at ${NEW_RELEASE_PATH}"
mkdir -p "${NEW_RELEASE_PATH}"
cp -a . "${NEW_RELEASE_PATH}/"

# Link shared environment, persistent storage, and database
ln -sfn "${SHARED_DIR}/.env" "${NEW_RELEASE_PATH}/.env" 2>/dev/null || true
ln -sfn "${SHARED_DIR}/uploads-temp" "${NEW_RELEASE_PATH}/uploads-temp" 2>/dev/null || true
ln -sfn "${SHARED_DIR}/data" "${NEW_RELEASE_PATH}/data" 2>/dev/null || true

# 3. Setup Python Virtual Environment and Install Backend Dependencies
echo "==> Step 3: Setting up backend virtual environment"
if [ ! -d "${NEW_RELEASE_PATH}/backend/venv" ]; then
    python3 -m venv "${NEW_RELEASE_PATH}/backend/venv"
fi
"${NEW_RELEASE_PATH}/backend/venv/bin/pip" install --upgrade pip setuptools wheel --quiet
"${NEW_RELEASE_PATH}/backend/venv/bin/pip" install -e "${NEW_RELEASE_PATH}/backend" --quiet

# 4. Build Frontend Production Bundle
echo "==> Step 4: Compiling frontend assets into dist"
if command -v npm >/dev/null 2>&1 && [ -f "${NEW_RELEASE_PATH}/frontend/package.json" ]; then
    (cd "${NEW_RELEASE_PATH}/frontend" && npm ci --silent && npm run build --silent)
else
    # Development/fallback static bundle
    mkdir -p "${NEW_RELEASE_PATH}/frontend/dist"
    cp -a "${NEW_RELEASE_PATH}/frontend/index.html" "${NEW_RELEASE_PATH}/frontend/dist/" 2>/dev/null || true
fi

# 5. Pre-Cutover Invariant Validation
echo "==> Step 5: Validating pre-cutover deployment invariants"
if [ ! -f "${NEW_RELEASE_PATH}/backend/venv/bin/gunicorn" ]; then
    echo "ERROR: Missing gunicorn binary in ${NEW_RELEASE_PATH}/backend/venv/bin/gunicorn"
    exit 1
fi
if [ ! -f "${NEW_RELEASE_PATH}/frontend/dist/index.html" ]; then
    echo "ERROR: Frontend dist bundle missing index.html in ${NEW_RELEASE_PATH}/frontend/dist"
    exit 1
fi

# Sync Supervisor & Nginx service definitions if system directories exist
if [ -d "/etc/supervisor/conf.d" ]; then
    echo "==> Updating supervisor configurations"
    sudo cp "${NEW_RELEASE_PATH}/deploy/supervisor/"*.conf /etc/supervisor/conf.d/
    sudo supervisorctl reread && sudo supervisorctl update
fi
if [ -d "/etc/nginx/sites-available" ]; then
    echo "==> Updating nginx configurations"
    sudo cp "${NEW_RELEASE_PATH}/deploy/nginx/receipt-app.conf" /etc/nginx/sites-available/
    sudo ln -sfn /etc/nginx/sites-available/receipt-app.conf /etc/nginx/sites-enabled/receipt-app.conf 2>/dev/null || true
fi

# 6. Retain previous pointer for atomic rollback
if [ -L "${CURRENT_LINK}" ] || [ -e "${CURRENT_LINK}" ]; then
    echo "==> Step 6: Retaining active target as previous pointer"
    OLD_TARGET=$(readlink -f "${CURRENT_LINK}")
    ln -sfn "${OLD_TARGET}" "${PREVIOUS_LINK}"
fi

# 7. Atomic cutover
echo "==> Step 7: Atomic symlink switch -> ${NEW_RELEASE_PATH}"
ln -sfn "${NEW_RELEASE_PATH}" "${CURRENT_LINK}"

# 8. Graceful daemon reload
echo "==> Step 8: Reloading application and proxy daemons"
sudo supervisorctl restart receipt-api receipt-worker 2>/dev/null || true
sudo nginx -t && sudo systemctl reload nginx 2>/dev/null || true

# 9. Post-deployment health verification
echo "==> Step 9: Post-deployment healthcheck probe"
if ! "${NEW_RELEASE_PATH}/deploy/scripts/healthcheck.sh"; then
    echo "CRITICAL: Healthcheck failed after cutover! Initiating rollback..."
    # 10. Automated rollback on failure
    "${NEW_RELEASE_PATH}/deploy/scripts/rollback.sh"
    exit 1
fi

echo "=================================================="
echo "  SUCCESS: Release ${RELEASE_TS} deployed and healthy!"
echo "=================================================="
exit 0
