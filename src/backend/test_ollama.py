import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chat.configuration import ChatConfigurationService, build_chat_service
from chat.errors import ChatError
from chat.ollama_client import OllamaClient
from chat.service import ChatService
from repositories.chat_configuration import EnvChatConfigurationRepository
from test_chat import FakeGraph, TODAY


def response(answer):
    return {"done": True, "done_reason": "stop", "model": "gemma4:31b", "message": {"content": json.dumps(answer)}}


class OllamaTests(unittest.TestCase):
    def test_free_form_question_identifies_equity_and_uses_ontop(self):
        graph = FakeGraph()
        client = OllamaClient()
        service = ChatService(graph, client, clock=lambda: TODAY,
                              security_search=lambda q: {"items": [{"symbol": "RELIANCE", "name": "Reliance"}]})
        source = graph.rows[0]["patternId"]
        with patch("chat.ollama_client.post_json", side_effect=[response({"target": "Reliance"}), response({"summaryCode": "SETUPS_PRESENT", "sourceIds": [source]})]) as call:
            result = service.answer({"message": "Hey, can you take a look at Reliance for me?", "contextSymbol": "TCS"}, "u")
        self.assertEqual(["RELIANCE"], graph.calls)
        self.assertEqual("ollama", result["provenance"]["provider"])
        self.assertEqual("gemma4:31b", result["provenance"]["model"])
        for args in call.call_args_list:
            body = json.loads(args.args[1])
            self.assertEqual("gemma4:31b-cloud", body["model"])
            self.assertFalse(body["stream"])
            self.assertNotIn("format", body)  # Cloud does not enforce schemas.

    def test_invalid_or_incomplete_model_outputs_do_not_become_evidence(self):
        client = OllamaClient()
        for value in (response({"summaryCode": "BUY", "sourceIds": []}),
                      response({"summaryCode": "NO_CURRENT_SETUP", "sourceIds": ["invented"]}),
                      {"done": False, "message": {"content": "{}"}}):
            with self.subTest(value=value), patch("chat.ollama_client.post_json", return_value=value), self.assertRaises(ChatError):
                client.summarize({"summaryCode": "NO_CURRENT_SETUP", "setups": []}, {})
        with patch("chat.ollama_client.post_json", return_value=response({"target": ["RELIANCE"]})), self.assertRaises(ChatError):
            client.resolve_target("anything")

    def test_ollama_is_default_and_settings_save_without_gemini_key(self):
        self.assertTrue(build_chat_service({"CHAT_ENABLED": "true"}).capabilities()["enabled"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            service = ChatConfigurationService(EnvChatConfigurationRepository(path), {})
            chat, public = service.save({"enabled": True, "provider": "ollama", "model": "gemma4:31b-cloud",
                                         "ontologyUrl": "http://127.0.0.1:8088/sparql",
                                         "ollamaUrl": "http://127.0.0.1:11434", "timeoutSeconds": 30})
            self.assertIsInstance(chat.model, OllamaClient)
            self.assertEqual("ollama", public["provider"])
            self.assertFalse(public["apiKeyConfigured"])
            self.assertIn("OLLAMA_MODEL=gemma4:31b-cloud", path.read_text())
            self.assertEqual(30, chat.model.timeout)
            with self.assertRaises(ValueError):
                service.save({"enabled": True, "model": "gemma4:31b-cloud", "ontologyUrl": "http://127.0.0.1:8088/sparql", "ollamaUrl": "http://user:password@localhost"})
