import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from chat.configuration import ChatConfigurationService, build_chat_service
from repositories.chat_configuration import EnvChatConfigurationRepository


class ChatConfigurationTests(unittest.TestCase):
    def test_atomic_save_preserves_unrelated_settings_and_never_returns_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('DATABASE_URL=keep-existing-value\n# preserve comment\nGEMINI_API_KEY=existing-key\n')
            environment = {'CHAT_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'existing-key'}
            service = ChatConfigurationService(EnvChatConfigurationRepository(path), environment)
            chat, public = service.save({'enabled': True, 'model': 'test-model', 'ontologyUrl': 'http://127.0.0.1:8088/sparql'})
            self.assertTrue(chat.capabilities()['enabled'])
            self.assertTrue(public['apiKeyConfigured'])
            self.assertNotIn('existing-key', json.dumps(public))
            self.assertNotIn('existing-key', json.dumps(chat.capabilities()))
            text = path.read_text()
            self.assertIn('DATABASE_URL=keep-existing-value', text)
            self.assertIn('# preserve comment', text)
            self.assertIn('GEMINI_API_KEY=existing-key', text)
            self.assertEqual('test-model', service.get()['model'])
            self.assertIs(chat, service.chat_service)

    def test_bad_settings_cannot_inject_env_or_enable_incomplete_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            service = ChatConfigurationService(EnvChatConfigurationRepository(path), {'CHAT_PROVIDER': 'gemini'})
            base = {'enabled': True, 'model': 'test-model', 'ontologyUrl': 'http://127.0.0.1:8088/sparql'}
            for payload in (base, {**base, 'apiKey': 'key\nJWT_SECRET=oops'}, {**base, 'model': '../invalid'}, {**base, 'enabled': 'true'}, {**base, 'extra': 'not-allowed'}):
                with self.subTest(payload=payload), self.assertRaises(ValueError): service.save(payload)
            self.assertFalse(path.exists())

    def test_configuration_status_reports_missing_and_invalid_values_without_credentials(self):
        chat = build_chat_service({'CHAT_PROVIDER': 'gemini', 'CHAT_ENABLED': 'true', 'ONTOP_URL': 'bad', 'GEMINI_MODEL': 'bad/model', 'GEMINI_API_KEY': 'secret'})
        status = chat.capabilities()
        self.assertFalse(status['enabled'])
        self.assertNotIn('secret', json.dumps(status))
        self.assertEqual('invalid', status['configuration']['checks'][1]['status'])

    def test_timeout_defaults_can_be_changed_and_invalid_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {'CHAT_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'secret'}
            service = ChatConfigurationService(EnvChatConfigurationRepository(Path(directory) / '.env'), environment)
            self.assertEqual(45, service.get()['timeoutSeconds'])
            base = {'enabled': True, 'model': 'test-model', 'ontologyUrl': 'http://127.0.0.1:8088/sparql'}
            chat, public = service.save({**base, 'timeoutSeconds': 60})
            self.assertEqual(60, chat.model.timeout)
            self.assertEqual(60, public['timeoutSeconds'])
            self.assertEqual('60', environment['GEMINI_TIMEOUT_SECONDS'])
            for value in (0, 121, True, 45.5, '60'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    service.save({**base, 'timeoutSeconds': value})


class ChatConfigurationHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_server
        from repositories.memory import InMemoryUserRepository
        cls.directory = tempfile.TemporaryDirectory()
        cls.settings = ChatConfigurationService(EnvChatConfigurationRepository(Path(cls.directory.name) / '.env'), {})
        cls.users = InMemoryUserRepository()
        cls.server = create_server(port=0, repository=cls.users, chat_configuration_service=cls.settings)
        service = cls.server.RequestHandlerClass.service
        service.register('member@chat.test', 'password123', 'password123')
        service.register('admin@chat.test', 'password123', 'password123')
        cls.users.get_by_email('admin@chat.test')['is_admin'] = True
        cls.member = service.login('member@chat.test', 'password123').access_token
        cls.admin = service.login('admin@chat.test', 'password123').access_token
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/api/admin/chat/configuration'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.directory.cleanup()

    def test_admin_boundary_and_hot_apply_without_exposing_secrets(self):
        for token, expected in ((None, 401), (self.member, 403)):
            for method in ('GET', 'PATCH'):
                headers = {'Authorization': 'Bearer ' + token} if token else {}
                with self.assertRaises(HTTPError) as failed: urlopen(Request(self.url, method=method, headers=headers))
                self.assertEqual(expected, failed.exception.code)
        payload = {'enabled': True, 'model': 'test-model', 'ontologyUrl': 'http://127.0.0.1:8088/sparql', 'apiKey': 'never-return-this'}
        with urlopen(Request(self.url, method='PATCH', data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + self.admin, 'Content-Type': 'application/json'})) as response:
            result = json.load(response)
        self.assertTrue(result['configuration']['apiKeyConfigured'])
        self.assertNotIn('never-return-this', json.dumps(result))
        with urlopen(Request(self.url.replace('/admin/chat/configuration', '/chat/capabilities'), headers={'Authorization': 'Bearer ' + self.member})) as response:
            self.assertTrue(json.load(response)['enabled'])
