from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from repositories.patterns import PatternConcurrencyError, PostgresPatternRepository


class RecordingCursor:
    def __init__(self, row=None):
        self.row = row
        self.executed = []
        self.description = [SimpleNamespace(name=name) for name in (row or {}).keys()]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def execute(self, statement, parameters=None):
        self.executed.append((statement, parameters))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [] if self.row is None else [self.row]


class RecordingConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


class PostgresPatternRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        self.returned = {
            "id": "00000000-0000-0000-0000-000000000101",
            "isin": "INE000000001", "pattern_type": "BASE-VCP",
            "state": "FORMING", "state_version": 1,
        }
        self.cursor = RecordingCursor(self.returned)
        self.connection = RecordingConnection(self.cursor)
        self.repository = object.__new__(PostgresPatternRepository)
        self.repository._connect = lambda: self.connection

    def test_create_instance_and_initial_event_commit_atomically(self):
        values = {
            "isin": "INE000000001", "pattern_class": "BASE",
            "pattern_type": "BASE-VCP", "variant": "VCP-3C",
            "start_date": date(2026, 8, 1), "detection_date": date(2026, 9, 1),
            "last_updated_date": date(2026, 9, 1), "state": "FORMING",
            "state_version": 1, "quality_score": Decimal("80"),
            "measurements": {"depth": Decimal("12")},
            "supporting_patterns": ("TREND-S2",),
            "configuration_version": "v1", "engine_version": "v1",
            "feature_version": "features-v1", "adjustment_version": "adjusted-v1",
            "active_deduplication_key": "stable-key",
        }
        event = {
            "event_type": "PATTERN_DETECTED", "state_version": 1,
            "previous_state": None, "new_state": "FORMING",
            "previous_values": {}, "new_values": {"state": "FORMING"},
            "effective_date": date(2026, 9, 1),
        }

        with patch(
            "repositories.patterns.uuid4",
            side_effect=[
                "00000000-0000-0000-0000-000000000101",
                "00000000-0000-0000-0000-000000000102",
            ],
        ):
            created = self.repository.create_pattern(values, event)

        self.assertEqual(self.returned, created)
        self.assertEqual(2, len(self.cursor.executed))
        instance_statement, instance_parameters = self.cursor.executed[0]
        event_statement, event_parameters = self.cursor.executed[1]
        self.assertIn("INSERT INTO pattern_instances", instance_statement)
        self.assertIn("INSERT INTO pattern_events", event_statement)
        self.assertEqual('{"depth": "12"}', instance_parameters["measurements"])
        self.assertEqual('["TREND-S2"]', instance_parameters["supporting_patterns"])
        self.assertEqual('{"state": "FORMING"}', event_parameters["new_values"])
        self.assertEqual(1, self.connection.commit_count)

    def test_active_load_is_parameterized_and_excludes_terminal_rows(self):
        self.cursor.row = None
        self.cursor.description = []

        self.repository.load_active_patterns("INE000000001", "BASE-VCP")

        statement, parameters = self.cursor.executed[0]
        self.assertIn("terminal_date IS NULL", statement)
        self.assertIn("%s::text IS NULL", statement)
        self.assertEqual(
            ("INE000000001", "BASE-VCP", "BASE-VCP"),
            parameters,
        )

    def test_update_uses_optimistic_version_and_commits_event_atomically(self):
        event = {
            "event_type": "STATE_CHANGED", "state_version": 2,
            "previous_state": "FORMING", "new_state": "READY",
            "previous_values": {"state": "FORMING"},
            "new_values": {"state": "READY"},
            "effective_date": date(2026, 9, 2),
        }

        updated = self.repository.update_pattern(
            self.returned["id"], 1,
            {
                "state": "READY", "last_updated_date": date(2026, 9, 2),
                "terminal_date": None, "measurements": {},
                "supporting_patterns": (),
            },
            event,
        )

        update_statement, update_parameters = self.cursor.executed[0]
        self.assertEqual(self.returned, updated)
        self.assertIn("state_version = %(new_state_version)s", update_statement)
        self.assertIn("terminal_date IS NULL", update_statement)
        self.assertEqual(1, update_parameters["expected_state_version"])
        self.assertEqual(2, update_parameters["new_state_version"])
        self.assertIn("INSERT INTO pattern_events", self.cursor.executed[1][0])
        self.assertEqual(1, self.connection.commit_count)

    def test_update_rejects_concurrent_or_terminal_instance(self):
        self.cursor.row = None
        self.cursor.description = []

        with self.assertRaises(PatternConcurrencyError):
            self.repository.update_pattern(
                self.returned["id"], 2,
                {"state": "READY", "last_updated_date": date(2026, 9, 2)},
                None,
            )

        self.assertEqual(0, self.connection.commit_count)

    def test_security_transaction_commits_once_and_enforces_isin_scope(self):
        with self.repository.security_transaction("INE000000001") as transaction:
            with self.assertRaisesRegex(ValueError, "cannot cross security"):
                transaction.load_active_patterns("INE000000002")

        self.assertEqual(1, self.connection.commit_count)
        self.assertEqual(0, self.connection.rollback_count)
        self.assertEqual(1, self.connection.close_count)

    def test_security_transaction_rolls_back_on_stage_failure(self):
        with self.assertRaisesRegex(RuntimeError, "detector failed"):
            with self.repository.security_transaction("INE000000001"):
                raise RuntimeError("detector failed")

        self.assertEqual(0, self.connection.commit_count)
        self.assertEqual(1, self.connection.rollback_count)
        self.assertEqual(1, self.connection.close_count)


if __name__ == "__main__":
    unittest.main()
