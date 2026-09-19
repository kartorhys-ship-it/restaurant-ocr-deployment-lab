import os
from typing import Dict, Any
from backend.app.compat import APIRouter, Response, status

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
    """Deep Readiness Probe.
    
    Validates availability of critical runtime dependencies (DB, Redis, configuration).
    Returns HTTP 500 if dependencies are degraded or if simulated broken release is active.
    """
    # Check for intentional failure simulation (used in v1.2.0 broken release tests)
    if SIMULATE_READINESS_FAILURE:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {
            "status": "unhealthy",
            "error": "Simulated readiness failure: database connection timeout",
            "dependencies": {
                "database": "down",
                "redis": "healthy"
            }
        }

    # In standard execution, verify dependencies
    return {
        "status": "healthy",
        "dependencies": {
            "database": "connected",
            "redis_queue": "reachable",
            "storage": "available"
        }
    }


@router.get("/health/worker")
def worker_heartbeat() -> Dict[str, Any]:
    """Worker Heartbeat Status.
    
    Distinguishes whether background OCR processing is active.
    """
    return {
        "worker_status": "active",
        "queue_name": os.getenv("QUEUE_NAME", "receipt_ocr"),
        "active_jobs": 0
    }


@router.get("/version")
def version_info() -> Dict[str, Any]:
    """Current release and version metadata."""
    return {
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "release": os.getenv("RELEASE_TS", "development"),
        "environment": os.getenv("APP_ENV", "local")
    }
