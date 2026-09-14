from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest

from data_pipeline.benchmark_history import BenchmarkHistoryService


class Repository:
    def __init__(self, date_range=(None, None)):
        self.date_range = date_range
        self.persisted = []

    def get_index_bar_date_range(self, index_code):
        self.requested_index = index_code
        return self.date_range

    def upsert_index_bars(self, index_code, bars):
        self.persisted.extend(bars)
        return len(bars)


class Client:
    def __init__(self):
        self.requests = []

    def fetch_index_history(self, index_name, from_date, to_date):
        self.requests.append((index_name, from_date, to_date))
        return [SimpleNamespace(
            index_name=index_name, trading_date=to_date,
            open_price=Decimal("100"), high_price=Decimal("102"),
            low_price=Decimal("99"), close_price=Decimal("101"),
            volume=None, source_checksum="checksum",
        )]


class BenchmarkHistoryServiceTestCase(unittest.TestCase):
    def test_first_run_downloads_full_requested_history(self):
        repository, client = Repository(), Client()

        written = BenchmarkHistoryService(repository, client).ensure_history(
            date(2016, 9, 9), date(2026, 9, 9)
        )

        self.assertEqual(2, written)
        self.assertEqual(
            [
                ("NIFTY 500", date(2016, 9, 9), date(2026, 9, 9)),
                ("NIFTY 50", date(2016, 9, 9), date(2026, 9, 9)),
            ],
            client.requests,
        )
        self.assertEqual("NSE", repository.persisted[0]["source_name"])

    def test_incremental_run_downloads_only_missing_tail(self):
        repository = Repository((date(2016, 9, 9), date(2026, 9, 8)))
        client = Client()

        BenchmarkHistoryService(repository, client).ensure_history(
            date(2016, 9, 9), date(2026, 9, 9)
        )

        self.assertEqual(
            [
                ("NIFTY 500", date(2026, 9, 9), date(2026, 9, 9)),
                ("NIFTY 50", date(2026, 9, 9), date(2026, 9, 9)),
            ],
            client.requests,
        )

    def test_current_history_avoids_an_nse_request(self):
        repository = Repository((date(2016, 9, 9), date(2026, 9, 9)))
        client = Client()

        written = BenchmarkHistoryService(repository, client).ensure_history(
            date(2020, 1, 1), date(2026, 9, 9)
        )

        self.assertEqual(0, written)
        self.assertEqual([], client.requests)


if __name__ == "__main__":
    unittest.main()
