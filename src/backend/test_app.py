import base64
import json
import threading
import unittest
from datetime import date
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

from app import InMemoryUserRepository, create_server
from repositories.pattern_queries import InMemoryPatternQueryRepository
from repositories.research import InMemoryResearchRepository


class EmptyReplayEvaluator:
    def evaluate(self, security, as_of_date, versions):
        return []


class FakeAdminPipelineService:
    RUN_ID = UUID("00000000-0000-0000-0000-000000000123")

    def __init__(self): self.started = []; self.controls = []
    def list_equities(self, query):
        return {"items": [{"isin": "INE002A01018", "symbol": "RELIANCE"}], "page": 1, "pageSize": 25, "totalItems": 1, "totalPages": 1}
    def list_runs(self, query): return {"items": [], "page": 1, "pageSize": 10, "totalItems": 0, "totalPages": 0}
    def get_run(self, run_id, query=None): return {"run": {"runId": run_id, "status": "RUNNING", "items": []}}
    def start(self, payload, requested_by):
        self.started.append((payload, requested_by))
        return {"run": {"runId": self.RUN_ID, "status": "PENDING", "items": []}}
    def pause(self, run_id):
        self.controls.append(("pause", run_id))
        return {"run": {"runId": run_id, "status": "PAUSED", "items": []}}
    def resume(self, run_id):
        self.controls.append(("resume", run_id))
        return {"run": {"runId": run_id, "status": "PENDING", "items": []}}
    def terminate(self, run_id):
        self.controls.append(("terminate", run_id))
        return {"run": {"runId": run_id, "status": "TERMINATED", "items": []}}


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = InMemoryUserRepository()
        cls.pattern_repository = InMemoryPatternQueryRepository()
        cls.research_repository = InMemoryResearchRepository()
        cls.admin_pipeline_service = FakeAdminPipelineService()
        cls.server = create_server(
            port=0, repository=cls.repository,
            pattern_repository=cls.pattern_repository,
            research_repository=cls.research_repository,
            replay_evaluator=EmptyReplayEvaluator(),
            admin_pipeline_service=cls.admin_pipeline_service,
        )
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

    def test_login_issues_token_and_protects_current_user(self) -> None:
        self.repository.create_user(
            "member@example.com",
            "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        )
        request = Request(
            f"{self.base_url}/api/login",
            method="POST",
            data=json.dumps({"email": "member@example.com", "password": "password123"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            payload = json.load(response)
        self.assertTrue(payload["accessToken"])

        authenticated_request = Request(
            f"{self.base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {payload['accessToken']}"},
        )
        with urlopen(authenticated_request) as response:
            current = json.load(response)
        self.assertEqual(current["user"]["email"], "member@example.com")
        self.assertTrue(current["accessToken"])
        encoded_claims = current["accessToken"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(
            encoded_claims + "=" * (-len(encoded_claims) % 4)
        ))
        self.assertEqual(12 * 60 * 60, claims["exp"] - claims["iat"])

    def test_authenticated_user_can_update_theme_preference(self) -> None:
        self.repository.create_user(
            "theme@example.com",
            "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        )
        login = Request(
            f"{self.base_url}/api/login", method="POST",
            data=json.dumps({"email": "theme@example.com", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(login) as response:
            token = json.load(response)["accessToken"]
        update = Request(
            f"{self.base_url}/api/profile", method="PATCH",
            data=json.dumps({"theme": "ocean"}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urlopen(update) as response:
            self.assertEqual("ocean", json.load(response)["user"]["theme"])
        current = Request(
            f"{self.base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(current) as response:
            self.assertEqual("ocean", json.load(response)["user"]["theme"])

        invalid = Request(
            f"{self.base_url}/api/profile", method="PATCH",
            data=json.dumps({"theme": "black"}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(invalid)
        self.assertEqual(400, context.exception.code)

    def test_unknown_endpoint_returns_404(self) -> None:
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/missing")
        self.assertEqual(context.exception.code, 404)

    def test_pattern_product_endpoints_require_bearer_token(self) -> None:
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/api/overview")
        self.assertEqual(context.exception.code, 401)
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/api/patterns/not-a-real-pattern/chart")
        self.assertEqual(context.exception.code, 401)
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/api/securities/search?q=reliance")
        self.assertEqual(context.exception.code, 401)
        request = Request(
            f"{self.base_url}/api/research/runs", method="POST",
            data=b"{}", headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request)
        self.assertEqual(context.exception.code, 401)

    def test_admin_pipeline_endpoints_reject_non_admin_users(self) -> None:
        self.repository.create_user(
            "ordinary@example.com",
            "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        )
        login = Request(
            f"{self.base_url}/api/login", method="POST",
            data=json.dumps({"email": "ordinary@example.com", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(login) as response: token = json.load(response)["accessToken"]
        request = Request(
            f"{self.base_url}/api/admin/equities",
            headers={"Authorization": f"Bearer {token}"},
        )
        with self.assertRaises(HTTPError) as context: urlopen(request)
        self.assertEqual(403, context.exception.code)

    def test_admin_can_list_equities_start_pipeline_and_read_status(self) -> None:
        admin = self.repository.create_user(
            "pipeline-admin@example.com",
            "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        )
        admin["is_admin"] = True
        login = Request(
            f"{self.base_url}/api/login", method="POST",
            data=json.dumps({"email": "pipeline-admin@example.com", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(login) as response: token = json.load(response)["accessToken"]
        headers = {"Authorization": f"Bearer {token}"}
        with urlopen(Request(f"{self.base_url}/api/admin/equities?page=1&pageSize=25", headers=headers)) as response:
            self.assertEqual("RELIANCE", json.load(response)["items"][0]["symbol"])
        start = Request(
            f"{self.base_url}/api/admin/pipeline/runs", method="POST",
            data=json.dumps({"isins": ["INE002A01018"]}).encode(),
            headers={**headers, "Content-Type": "application/json"},
        )
        with urlopen(start) as response:
            self.assertEqual(202, response.status)
            run_id = json.load(response)["run"]["runId"]
        with urlopen(Request(f"{self.base_url}/api/admin/pipeline/runs/{run_id}", headers=headers)) as response:
            self.assertEqual("RUNNING", json.load(response)["run"]["status"])
        control = Request(
            f"{self.base_url}/api/admin/pipeline/runs/{run_id}/pause",
            method="POST", data=b"{}", headers={**headers, "Content-Type": "application/json"},
        )
        with urlopen(control) as response:
            self.assertEqual(200, response.status)
            self.assertEqual("PAUSED", json.load(response)["run"]["status"])
        self.assertIn(("pause", run_id), self.admin_pipeline_service.controls)

    def test_authenticated_overview_returns_product_contract(self) -> None:
        self.repository.create_user(
            "overview@example.com",
            "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        )
        login = Request(
            f"{self.base_url}/api/login", method="POST",
            data=json.dumps({"email": "overview@example.com", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(login) as response:
            token = json.load(response)["accessToken"]
        request = Request(f"{self.base_url}/api/overview", headers={"Authorization": f"Bearer {token}"})
        with urlopen(request) as response:
            payload = json.load(response)
        self.assertIn("countsByState", payload)
        self.assertIn("topSetups", payload)

    def test_authenticated_reliance_fingerprint_returns_data_and_lineage_contract(self) -> None:
        self.repository.create_user(
            "fingerprint@example.com",
            "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        )
        self.pattern_repository.securities["INE002A01018"] = {
            "isin": "INE002A01018", "symbol": "RELIANCE",
            "company_name": "Reliance Industries Limited",
            "sector_code": "ENERGY", "sector_name": "Energy",
        }
        self.pattern_repository.features.append({
            "isin": "INE002A01018", "trading_date": date(2024, 1, 5),
            "feature_version": "phase18-features-v1", "close_price": Decimal("1303.85"),
            "ema_20": None, "sma_50": None, "sma_200": None,
        })
        login = Request(
            f"{self.base_url}/api/login", method="POST",
            data=json.dumps({"email": "fingerprint@example.com", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(login) as response:
            token = json.load(response)["accessToken"]
        request = Request(
            f"{self.base_url}/api/securities/INE002A01018/fingerprint?asOf=2024-01-05",
            headers={"Authorization": f"Bearer {token}"},
        )

        with urlopen(request) as response:
            payload = json.load(response)

        self.assertEqual("RELIANCE", payload["security"]["symbol"])
        self.assertEqual("2024-01-05", payload["dataAsOf"])
        self.assertEqual("phase18-features-v1", payload["lineage"]["featureVersion"])

        search = Request(
            f"{self.base_url}/api/securities/search?q=reliance",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(search) as response:
            matches = json.load(response)["items"]
        self.assertEqual("INE002A01018", matches[0]["isin"])

    def test_authenticated_research_run_and_results_contract(self) -> None:
        self.repository.create_user(
            "research@example.com",
            "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        )
        login = Request(
            f"{self.base_url}/api/login", method="POST",
            data=json.dumps({"email": "research@example.com", "password": "password123"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(login) as response:
            token = json.load(response)["accessToken"]
        request = Request(
            f"{self.base_url}/api/research/runs", method="POST",
            data=json.dumps({
                "fromDate": "2026-01-01", "toDate": "2026-01-02",
                "universe": {"indexCode": "NIFTY500"},
                "versions": {"engine": "e1", "configuration": "c1", "feature": "f1", "adjustment": "a1"},
            }).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        with urlopen(request) as response:
            self.assertEqual(201, response.status)
            run_id = json.load(response)["run"]["runId"]
        results = Request(
            f"{self.base_url}/api/research/runs/{run_id}/results",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(results) as response:
            payload = json.load(response)
        self.assertEqual("COMPLETED", payload["run"]["status"])
        self.assertEqual(0, payload["summary"]["totalEntries"])


if __name__ == "__main__":
    unittest.main()
