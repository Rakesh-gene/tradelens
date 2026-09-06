from datetime import date
from types import SimpleNamespace
import unittest

from repositories.research import PostgresResearchRepository


class RecordingCursor:
    def __init__(self):
        self.executed = []
        self.description = [SimpleNamespace(name="isin")]

    def __enter__(self): return self
    def __exit__(self, *args): return None
    def execute(self, statement, parameters=None): self.executed.append((statement, parameters))
    def fetchall(self): return []


class RecordingConnection:
    def __init__(self, cursor): self.cursor_instance = cursor
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def cursor(self): return self.cursor_instance


class ResearchRepositoryTestCase(unittest.TestCase):
    def test_historical_universe_query_uses_effective_membership_parameters(self):
        cursor = RecordingCursor()
        repository = object.__new__(PostgresResearchRepository)
        repository._connect = lambda: RecordingConnection(cursor)
        as_of = date(2020, 3, 12)

        repository.list_historical_universe("NIFTY500", as_of)

        statement, parameters = cursor.executed[0]
        self.assertIn("index_constituent_memberships", statement)
        self.assertIn("membership.effective_from <= %s", statement)
        self.assertIn("membership.effective_to >= %s", statement)
        self.assertEqual((as_of, as_of, as_of, "NIFTY500", as_of, as_of), parameters)


if __name__ == "__main__":
    unittest.main()
