"""Smoke tests verifying FastAPI application boot, configuration, and router initialization."""

import unittest
from backend.app.main import app, create_app
from backend.app.compat import Response


class TestApplicationSmoke(unittest.TestCase):
    """Verifies that the application boots without import or configuration errors."""

    def test_app_instance_created(self):
        self.assertIsNotNone(app)
        self.assertEqual(app.title, "Restaurant Receipt & OCR Expense Platform API")
        self.assertEqual(app.version, "1.0.0")

    def test_create_app_factory(self):
        new_app = create_app()
        self.assertIsNotNone(new_app)
        self.assertEqual(len(new_app.routers), 2)

    def test_routes_mounted(self):
        route_paths = []
        for router in app.routers:
            for method, path, _ in getattr(router, "routes", []):
                route_paths.append((method, path))

        expected_routes = [
            ("GET", "/api/health/live"),
            ("GET", "/api/health/ready"),
            ("GET", "/api/health/worker"),
            ("GET", "/api/version"),
            ("POST", "/api/receipts"),
            ("GET", "/api/receipts"),
        ]

        for expected_method, expected_path in expected_routes:
            self.assertIn(
                (expected_method, expected_path),
                route_paths,
                f"Expected route {expected_method} {expected_path} to be registered on FastAPI app"
            )


if __name__ == "__main__":
    unittest.main()
