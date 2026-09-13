import os
import unittest
from unittest.mock import Mock, patch

import server


@unittest.skipIf(server.psycopg is None, 'psycopg is not installed')
class DatabaseStartupTestCase(unittest.TestCase):
    def test_transient_connection_failure_is_retried(self):
        repository = object()
        factory = Mock(side_effect=[
            server.psycopg.OperationalError('database is starting'),
            repository,
        ])
        environment = {
            'DATABASE_URL': 'postgresql://example.invalid/tradelens',
            'DATABASE_STARTUP_ATTEMPTS': '3',
            'DATABASE_STARTUP_DELAY_SECONDS': '0',
        }

        with patch.dict(os.environ, environment), patch.object(
            server, 'PostgresUserRepository', factory,
        ), patch.object(server, 'sleep') as wait:
            result = server.build_repository()

        self.assertIs(repository, result)
        self.assertEqual(2, factory.call_count)
        wait.assert_called_once_with(0)

    def test_non_connection_error_is_not_retried(self):
        factory = Mock(side_effect=ValueError('invalid migration'))
        with patch.dict(os.environ, {
            'DATABASE_URL': 'postgresql://example.invalid/tradelens',
            'DATABASE_STARTUP_ATTEMPTS': '3',
        }), patch.object(server, 'PostgresUserRepository', factory), patch.object(
            server, 'sleep',
        ) as wait:
            with self.assertRaisesRegex(ValueError, 'invalid migration'):
                server.build_repository()

        factory.assert_called_once()
        wait.assert_not_called()


if __name__ == '__main__':
    unittest.main()
