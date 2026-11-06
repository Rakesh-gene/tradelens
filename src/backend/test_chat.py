import json
import threading
import unittest
from copy import deepcopy
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from chat.errors import ChatError
from chat.gemini_client import GeminiClient
from chat.service import CAPABILITY, ChatService, release_manifest
from repositories.knowledge_graph import OntopKnowledgeGraphRepository, current_setup_query

IDENTIFIER = "00000000-0000-4000-8000-000000000001"
TODAY = date(2026, 11, 1)


def evidence():
    return {"security": "urn:tradelens:security:INE002A01018", "symbol": "RELIANCE", "name": "Reliance",
            "dataAsOf": "2026-10-30", "featureDate": "2026-10-30", "patternDate": "2026-10-30",
            "snapshot": "urn:tradelens:snapshot:fixture", "patternId": IDENTIFIER,
            "patternType": "BASE-VCP", "state": "urn:tradelens:ontology:READY",
            "evidenceDate": "2026-10-30", "detectedDate": "2026-10-20", "quality": "90", "setup": "85",
            "pivot": "100", "engineVersion": "engine1", "configurationVersion": "config1",
            "featureVersion": "features1", "adjustmentVersion": "adjust1"}


class FakeGraph:
    def __init__(self, rows=None): self.rows = rows if rows is not None else [evidence()]; self.calls = []
    def current_setups(self, symbol): self.calls.append(symbol); return deepcopy(self.rows)


class FakeModel:
    def __init__(self): self.calls = []
    def summarize(self, facts, definition): self.calls.append(deepcopy(facts)); return {"model": "fake-gemini"}


class ChatServiceTests(unittest.TestCase):
    def setUp(self):
        self.graph, self.model = FakeGraph(), FakeModel()
        self.service = ChatService(self.graph, self.model, clock=lambda: TODAY)
        self.payload = {"message": CAPABILITY["question"], "symbol": "RELIANCE"}

    def test_returns_dated_grounded_setup_and_preserves_missing_values(self):
        result = self.service.answer(self.payload, "user1")
        self.assertEqual("2026-10-30", result["dataAsOf"])
        self.assertTrue(result["isStale"])
        self.assertTrue(result["isPartial"])
        self.assertEqual(90, result["setups"][0]["scores"]["quality"])
        self.assertIsNone(result["setups"][0]["scores"]["maturity"])
        self.assertEqual("READY", result["setups"][0]["state"])
        self.assertNotIn("snapshot", result["setups"][0])
        self.assertNotIn("INE002A01018", json.dumps(result))
        self.assertEqual("SETUPS_PRESENT", self.model.calls[0]["summaryCode"])
        self.assertEqual(7, len(release_manifest()["hashes"]))
        # Freeze the same browser contract consumed by the widget fixture.
        from pathlib import Path
        fixture = json.loads((Path(__file__).resolve().parents[1] / "frontend/test/fixtures/chat-equity-setup.json").read_text())
        self.assertEqual(set(fixture) - {"requestId"}, set(result))
        self.assertEqual(set(fixture["setups"][0]), set(result["setups"][0]))

    def test_other_questions_and_query_fragments_never_reach_graph_or_model(self):
        for change in ({"symbol": 'RELIANCE" } SERVICE <https://evil.test> {'}, {"symbol": "INE002A01018"}, {"userId": "victim"}):
            with self.subTest(change=change), self.assertRaises((ValueError, ChatError)):
                self.service.answer({**self.payload, **change}, "user1")
        self.assertEqual([], self.graph.calls)
        self.assertEqual([], self.model.calls)

    def test_missing_or_lagging_evaluation_is_not_a_zero(self):
        row = {key: value for key, value in evidence().items() if key in {"security", "symbol", "name", "dataAsOf", "featureDate"}}
        self.graph.rows = [row]
        result = self.service.answer(self.payload, "user1")
        self.assertEqual("insufficientEvidence", result["status"])
        self.assertEqual([], result["setups"])
        self.assertIn("not a verified zero", " ".join(result["warnings"]))

    def test_retained_evaluation_without_primary_setup_has_explicit_empty_answer(self):
        self.graph.rows = [{key: value for key, value in evidence().items() if key in {"security", "symbol", "name", "dataAsOf", "featureDate", "patternDate"}}]
        result = self.service.answer(self.payload, "user1")
        self.assertEqual("answered", result["status"])
        self.assertIn("No active daily primary setup", result["answer"])

    def test_future_conflicting_terminal_and_invalid_scores_are_rejected(self):
        for change in ({"evidenceDate": "2026-11-02"}, {"state": "urn:tradelens:ontology:FAILED"}, {"quality": "101"}, {"setup": "NaN"}, {"symbol": "OTHER"}, {"featureDate": "2026-11-01"}):
            with self.subTest(change=change):
                service = ChatService(FakeGraph([{**evidence(), **change}]), self.model, clock=lambda: TODAY)
                with self.assertRaises(ChatError) as error: service.answer(self.payload, "user1")
                self.assertEqual("ONTOLOGY_INVALID_EVIDENCE", error.exception.code)

    def test_disabled_and_rate_limit(self):
        with self.assertRaises(ChatError) as disabled:
            ChatService().answer(self.payload, "u")
        self.assertEqual("CHAT_NOT_CONFIGURED", disabled.exception.code)
        for _ in range(6): self.service.answer(self.payload, "user1")
        with self.assertRaises(ChatError) as limited: self.service.answer(self.payload, "user1")
        self.assertEqual(429, limited.exception.status)

    def test_provider_failure_releases_concurrency_slot(self):
        with patch.object(self.model, "summarize", side_effect=ChatError("FAILED", "Unavailable")):
            with self.assertRaises(ChatError): self.service.answer(self.payload, "user1")
        self.assertEqual("answered", self.service.answer(self.payload, "user1")["status"])

    def test_gemini_outage_preserves_real_ontology_evidence_with_explicit_label(self):
        for code in ('UPSTREAM_TIMEOUT', 'UPSTREAM_UNAVAILABLE', 'UPSTREAM_NETWORK_BLOCKED'):
            with self.subTest(code=code), patch.object(self.model, 'summarize', side_effect=ChatError(code, 'Unavailable')):
                result = self.service.answer(self.payload, 'user1')
                self.assertEqual('ontologyEvidenceOnly', result['provenance']['answerMode'])
                self.assertEqual(code, result['provenance']['geminiErrorCode'])
                self.assertIsNone(result['provenance']['model'])
                self.assertTrue(result['isPartial'])
                self.assertEqual(IDENTIFIER, result['setups'][0]['patternInstanceId'])
                self.assertIn('no LLM explanation was generated', ' '.join(result['warnings']))
        self.assertEqual(3, len(self.graph.calls))

    def test_registered_query_requires_inference_and_is_not_arbitrary_sql(self):
        query = current_setup_query("RELIANCE")
        self.assertIn("a tl:PrimarySetupSnapshot", query)
        self.assertIn('tl:symbol "RELIANCE"', query)
        self.assertIn("LIMIT 26", query)
        with self.assertRaises(ValueError): current_setup_query("X\" UNION {}")

    def test_natural_question_resolves_equity_and_overrides_page_context(self):
        search = lambda query: {"items": [{"symbol": "RELIANCE", "name": "Reliance Industries Limited"}]}
        service = ChatService(self.graph, self.model, security_search=search, clock=lambda: TODAY)
        for question in ('what is the setup in reliance today?', 'What setups does Reliance have today?', 'Show me the setup for Reliance Industries Limited today'):
            result = service.answer({"message": question, "contextSymbol": "TCS"}, "user1")
            self.assertEqual("RELIANCE", result["security"]["symbol"])
        self.assertEqual(["RELIANCE"] * 3, self.graph.calls)

    def test_ambiguous_and_missing_equity_have_actionable_errors(self):
        search = lambda query: {"items": [{"symbol": "RELIANCE"}, {"symbol": "RELINFRA"}]}
        service = ChatService(self.graph, self.model, security_search=search)
        with self.assertRaises(ChatError) as ambiguous:
            service.answer({"message": "what is the setup in rel today?"}, "user1")
        self.assertEqual("EQUITY_AMBIGUOUS", ambiguous.exception.code)
        with self.assertRaises(ChatError) as missing:
            service.answer({"message": "what is the setup today?"}, "user1")
        self.assertEqual("EQUITY_REQUIRED", missing.exception.code)
        self.assertEqual([], self.graph.calls)

    def test_prompt_limit_is_4000_and_free_form_wording_is_accepted(self):
        self.service.answer({**self.payload, "message": CAPABILITY["question"] + ' ' * 300}, "u")
        with self.assertRaises(ValueError):
            self.service.answer({**self.payload, "message": 'x' * 4001}, "u")
        result = self.service.answer({"message": "How is this one looking?", "contextSymbol": "RELIANCE"}, "u")
        self.assertEqual("RELIANCE", result["security"]["symbol"])
        self.assertEqual("equity_setup_today", result["intent"])


class GeminiBoundaryTests(unittest.TestCase):
    def test_constrained_response_rejects_invented_sources_and_blocked_answers(self):
        client = GeminiClient("never-log-this", "test-model")
        facts = {"summaryCode": "SETUPS_PRESENT", "setups": [{"sourceId": IDENTIFIER}]}
        for answer in ({"summaryCode": "SETUPS_PRESENT", "sourceIds": ["invented"]}, {"summaryCode": "BUY", "sourceIds": [IDENTIFIER]}, {"summaryCode": "SETUPS_PRESENT", "sourceIds": [IDENTIFIER], "price": 42}):
            raw = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(answer)}]}}]}
            with patch("chat.gemini_client.post_json", return_value=raw), self.assertRaises(ChatError):
                client.summarize(facts, CAPABILITY)
        raw = {"modelVersion": "pinned-version", "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"summaryCode": "SETUPS_PRESENT", "sourceIds": [IDENTIFIER]})}]}}]}
        with patch("chat.gemini_client.post_json", return_value=raw) as transport:
            self.assertEqual("pinned-version", client.summarize(facts, CAPABILITY)["model"])
            self.assertNotIn("never-log-this", transport.call_args.args[0])

    def test_flash_uses_model_supported_low_latency_thinking_controls(self):
        facts = {"summaryCode": "NO_CURRENT_SETUP", "setups": []}
        raw = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"summaryCode": "NO_CURRENT_SETUP", "sourceIds": []})}]}}]}
        for model, expected in (("gemini-3.8-flash", {"thinkingLevel": "low"}), ("gemini-2.5-flash", {"thinkingBudget": 0}), ("test-model", None)):
            with self.subTest(model=model), patch("chat.gemini_client.post_json", return_value=raw) as transport:
                GeminiClient("secret", model).summarize(facts, CAPABILITY)
                body = json.loads(transport.call_args.args[1])
                self.assertEqual(expected, body["generationConfig"].get("thinkingConfig"))

    def test_ontop_client_decodes_rdf_bindings_and_rejects_malformed_results(self):
        repository = OntopKnowledgeGraphRepository("http://127.0.0.1:8088/sparql")
        with patch("repositories.knowledge_graph.post_json", return_value={"results": {"bindings": [{"symbol": {"type": "literal", "value": "RELIANCE"}}]}}):
            self.assertEqual([{"symbol": "RELIANCE"}], repository.current_setups("RELIANCE"))
        with patch("repositories.knowledge_graph.post_json", return_value={"results": {"bindings": [{"symbol": "invalid"}]}}), self.assertRaises(ChatError):
            repository.current_setups("RELIANCE")


class ChatHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_server
        from repositories.memory import InMemoryUserRepository
        cls.server = create_server(port=0, repository=InMemoryUserRepository(), chat_service=ChatService(FakeGraph(), FakeModel(), clock=lambda: TODAY))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.token = cls.server.RequestHandlerClass.service.register("chat@example.com", "password123", "password123")
        cls.access = cls.server.RequestHandlerClass.service.login("chat@example.com", "password123").access_token

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, body, token=None):
        return urlopen(Request(self.url + "/api/chat/messages/", data=body, headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}))

    def test_auth_valid_request_unsupported_question_and_malformed_payload(self):
        with self.assertRaises(HTTPError) as missing: self.request(b"{}")
        self.assertEqual(401, missing.exception.code)
        for raw in (b"[]", b"{", b"x" * 5000):
            with self.subTest(raw=raw[:30]), self.assertRaises(HTTPError) as failure:
                self.request(raw, self.access)
            self.assertEqual(400, failure.exception.code)
            self.assertIn("requestId", json.load(failure.exception)["error"])
        with self.request(json.dumps({"symbol": "RELIANCE", "message": CAPABILITY["question"]}).encode(), self.access) as response:
            self.assertEqual("RELIANCE", json.load(response)["security"]["symbol"])
