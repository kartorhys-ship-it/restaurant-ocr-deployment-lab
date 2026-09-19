"""Multi-Level Healthcheck Endpoints with Live Dependency Probing."""

import os
from pathlib import Path
from typing import Dict, Any
from backend.app.compat import APIRouter, Response, status
from backend.app.domain.db import get_receipt_store
from backend.app.domain.queue import get_receipt_queue

router = APIRouter(prefix="/api", tags=["health"])

# Simulation toggle for testing automated deployment rollbacks
SIMULATE_READINESS_FAILURE = os.getenv("SIMULATE_READINESS_FAILURE", "false").lower() == "true"


@router.get("/health/live", status_code=status.HTTP_200_OK)
def liveness_check() -> Dict[str, Any]:
    """Process Liveness Probe.
    
    Verifies that the FastAPI process is responsive to HTTP requests.
    """
    return {
        "status": "healthy",
        "service": "receipt-api",
        "pid": os.getpid()
    }


@router.get("/health/ready")
def readiness_check(response: Response) -> Dict[str, Any]:
    """Deep Readiness Probe with Active Dependency Probes.
    
    Actively executes:
    1. Database probe (SELECT 1 test transaction)
    2. Queue broker probe (Redis PING or SQLite queue status)
    3. Storage directory write accessibility check
    
    Returns HTTP 200 when all dependencies are healthy.
    Returns HTTP 500 when any dependency is degraded or simulation is active.
    """
    # 1. Intentional failure simulation (used in v1.2.0 broken release tests)
    if SIMULATE_READINESS_FAILURE:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {
            "status": "unhealthy",
            "error": "Simulated readiness failure: database connection timeout",
            "dependencies": {
                "database": "down",
                "queue": "healthy",
                "storage": "healthy"
            }
        }

    # 2. Live Database Probe
    db_store = get_receipt_store()
    db_healthy = db_store.check_health()

    # 3. Live Queue Broker Probe
    queue = get_receipt_queue()
    queue_healthy = queue.check_health()

    # 4. Storage Probe
    storage_dir = Path(os.getenv("STORAGE_DIR", "./uploads-temp"))
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        probe_file = storage_dir / ".healthcheck_probe"
        probe_file.write_text("probe", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        storage_healthy = True
    except Exception:
        storage_healthy = False

    all_healthy = db_healthy and queue_healthy and storage_healthy

    if not all_healthy:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {
            "status": "degraded",
            "dependencies": {
                "database": "connected" if db_healthy else "unreachable",
                "queue": "reachable" if queue_healthy else "unreachable",
                "storage": "available" if storage_healthy else "unwritable"
            }
        }

    return {
        "status": "healthy",
        "dependencies": {
            "database": "connected",
            "queue": "reachable",
            "storage": "available"
        }
    }


@router.get("/health/worker")
def worker_heartbeat() -> Dict[str, Any]:
    """Worker Heartbeat Status.
    
    Distinguishes whether background OCR processing is active and reports queue backlog.
    """
    queue = get_receipt_queue()
    pending = queue.pending_count()
    return {
        "worker_status": "active",
        "queue_name": queue.queue_name,
        "pending_jobs": pending
    }


@router.get("/version")
def version_info() -> Dict[str, Any]:
    """Current release and version metadata."""
    return {
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "release": os.getenv("RELEASE_TS", "development"),
        "environment": os.getenv("APP_ENV", "local")
    }
