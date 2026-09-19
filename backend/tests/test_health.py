"""Tests for Multi-Level Healthcheck Endpoints and Dependency Probing."""

import unittest
from unittest.mock import patch
from backend.app.api.health import liveness_check, readiness_check, worker_heartbeat, version_info
from backend.app.compat import Response


class TestHealthEndpoints(unittest.TestCase):
    def test_liveness_returns_healthy(self):
        data = liveness_check()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "receipt-api")
        self.assertIn("pid", data)

    def test_readiness_returns_healthy_when_dependencies_up(self):
        resp = Response()
        data = readiness_check(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["dependencies"]["database"], "connected")
        self.assertEqual(data["dependencies"]["queue"], "reachable")
        self.assertEqual(data["dependencies"]["storage"], "available")

    def test_readiness_returns_500_when_database_fails(self):
        resp = Response()
        with patch("backend.app.domain.db.ReceiptStore.check_health", return_value=False):
            data = readiness_check(resp)
            self.assertEqual(resp.status_code, 500)
            self.assertEqual(data["status"], "degraded")
            self.assertEqual(data["dependencies"]["database"], "unreachable")

    def test_readiness_returns_500_when_simulation_enabled(self):
        resp = Response()
        with patch("backend.app.api.health.SIMULATE_READINESS_FAILURE", True):
            data = readiness_check(resp)
            self.assertEqual(resp.status_code, 500)
            self.assertEqual(data["status"], "unhealthy")

    def test_worker_heartbeat(self):
        data = worker_heartbeat()
        self.assertEqual(data["worker_status"], "active")
        self.assertIn("queue_name", data)
        self.assertIn("pending_jobs", data)

    def test_version_endpoint(self):
        data = version_info()
        self.assertIn("version", data)
        self.assertIn("release", data)


if __name__ == "__main__":
    unittest.main()
