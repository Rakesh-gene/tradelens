import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import InMemoryUserRepository, create_server


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = InMemoryUserRepository()
        cls.server = create_server(port=0, repository=cls.repository)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_health_endpoint(self) -> None:
        with urlopen(f"{self.base_url}/api/health") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(
                json.load(response),
                {"status": "ok", "service": "tradelens-backend"},
            )

    def test_registration_creates_user(self) -> None:
        request = Request(
            f"{self.base_url}/api/register",
            method="POST",
            data=json.dumps(
                {
                    "email": "new@example.com",
                    "password": "password123",
                    "confirmPassword": "password123",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urlopen(request) as response:
            self.assertEqual(response.status, 201)
            payload = json.load(response)
            self.assertEqual(payload["status"], "created")
            self.assertEqual(payload["user"]["email"], "new@example.com")
            self.assertTrue(payload["user"]["id"])

    def test_duplicate_registration_returns_400(self) -> None:
        self.repository.create_user("dup@example.com", "hash")
        request = Request(
            f"{self.base_url}/api/register",
            method="POST",
            data=json.dumps(
                {
                    "email": "dup@example.com",
                    "password": "password123",
                    "confirmPassword": "password123",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with self.assertRaises(HTTPError) as context:
            urlopen(request)
        self.assertEqual(context.exception.code, 400)

    def test_unknown_endpoint_returns_404(self) -> None:
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/missing")
        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
