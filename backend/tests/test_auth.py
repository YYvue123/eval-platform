import unittest

from fastapi.testclient import TestClient

from app.main import app


class AuthSmokeTest(unittest.TestCase):
    def test_login_and_dashboard(self):
        with TestClient(app) as client:
            res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
            self.assertEqual(res.status_code, 200)
            token = res.json()["access_token"]
            stats = client.get("/api/dashboard/stats", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(stats.status_code, 200)
            self.assertIn("user_count", stats.json())


if __name__ == "__main__":
    unittest.main()
