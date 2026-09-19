"""Tests for Multi-Level Healthcheck Endpoints."""

import unittest
from backend.app.api.health import liveness_check, readiness_check, version_info
from backend.app.compat import Response


class TestHealthEndpoints(unittest.TestCase):
    def test_liveness_returns_healthy(self):
        data = liveness_check()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "receipt-api")
        self.assertIn("pid", data)

    def test_readiness_returns_healthy(self):
        resp = Response()
        data = readiness_check(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("dependencies", data)

    def test_version_endpoint(self):
        data = version_info()
        self.assertIn("version", data)
        self.assertIn("release", data)


if __name__ == "__main__":
    unittest.main()

