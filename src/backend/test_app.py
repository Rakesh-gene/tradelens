import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from app import create_server


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(port=0)
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

    def test_unknown_endpoint_returns_404(self) -> None:
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/missing")
        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
