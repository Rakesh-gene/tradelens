from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest

from indices.service import IndexPipelineService, IndexQueryService
from pattern_engine.configuration import load_pattern_engine_configuration
from repositories.indices import InMemoryIndexRepository
from data_pipeline.normalization import parse_index_history_response


class FakeMarket:
    def __init__(self): self.updates = []; self.bars = []
    def create_import_run(self, *args, **kwargs): return "index-run"
    def update_import_run(self, *args, **kwargs): self.updates.append((args, kwargs))
    def get_index_bar_date_range(self, code): return (None, None)
    def upsert_index_bars(self, code, bars): self.bars.extend(bars); return len(bars)


class FakeNse:
    def fetch_index_history(self, name, from_date, to_date):
        return [SimpleNamespace(
            index_name=name, trading_date=to_date, open_price=Decimal("100"),
            high_price=Decimal("102"), low_price=Decimal("99"), close_price=Decimal("101"),
            volume=1000, source_checksum="checksum",
        )]


class FakeRecovery:
    def __init__(self): self.calls = []
    def rebuild_security(self, *args, **kwargs):
        self.calls.append((args, kwargs)); return {"status": "COMPLETED"}


class IndexServiceTestCase(unittest.TestCase):
    def test_incomplete_index_candle_is_skipped_without_fabricating_ohlc(self):
        rows = parse_index_history_response([
            {"Date": "21-Dec-2016", "Open": "-", "High": "100", "Low": "99", "Close": "100"},
            {"Date": "22-Dec-2016", "Open": "100", "High": "102", "Low": "99", "Close": "101"},
        ], "NIFTY MIDCAP 150")

        self.assertEqual([date(2016, 12, 22)], [row.trading_date for row in rows])

    def test_query_groups_indices_and_exposes_rotation_and_setup(self):
        repository = InMemoryIndexRepository([{
            "code": "NIFTY IT", "name": "NIFTY IT", "category": "SECTORAL",
            "engine_isin": "INIDX0000180", "data_as_of": date(2026, 9, 11),
            "last_close": Decimal("40000"), "previous_close": Decimal("39800"),
            "relative_strength_1m": Decimal("6"), "relative_strength_3m": Decimal("9"),
            "rotation_history": [
                {"date": date(2026, 9, 5), "strength": Decimal("5"), "momentum": Decimal("1")},
                {"date": date(2026, 9, 8), "strength": Decimal("6"), "momentum": Decimal("2")},
                {"date": date(2026, 9, 11), "strength": Decimal("9"), "momentum": Decimal("3")},
            ],
            "pattern_id": "pattern-1", "pattern_type": "BASE-VCP", "state": "READY",
            "setup_score": Decimal("84"), "pivot_price": Decimal("40500"),
        }])
        self.assertEqual(1, repository.reconcile_quadrants(date(2026, 9, 11)))
        service = IndexQueryService(repository)

        payload = service.list()

        self.assertEqual(1, payload["count"])
        self.assertEqual("LEADING", payload["items"][0]["rotation"]["zone"])
        self.assertEqual(3, len(payload["items"][0]["rotation"]["trail"]))
        self.assertEqual(date(2026, 9, 5), payload["items"][0]["rotation"]["trail"][0]["date"])
        self.assertEqual("pattern-1", payload["items"][0]["primarySetup"]["patternInstanceId"])
        self.assertEqual(1, next(group for group in payload["categories"] if group["id"] == "SECTORAL")["count"])
        self.assertEqual("QUADRANT_ENTERED", payload["activity"][0]["eventType"])
        self.assertEqual("NIFTY IT", payload["activity"][0]["index"]["name"])
        self.assertNotIn("engineSecurityId", payload["items"][0])
        self.assertNotIn("engineSecurityId", payload["activity"][0]["index"])
        self.assertEqual(
            {"isin": "INIDX0000180", "symbol": "NIFTY IT", "name": "NIFTY IT"},
            service.resolve_security("nifty it"),
        )
        with self.assertRaises(LookupError):
            service.resolve_security("unknown")

        repository.rows[0]["relative_strength_1m"] = Decimal("1")
        repository.rows[0]["data_as_of"] = date(2026, 9, 12)
        self.assertEqual(1, repository.reconcile_quadrants(date(2026, 9, 12)))
        self.assertEqual("QUADRANT_CHANGED", repository.events[0]["event_type"])
        self.assertEqual("WEAKENING", repository.events[0]["new_state"])

    def test_pipeline_imports_mirrors_and_scans_daily_weekly_monthly(self):
        indices = InMemoryIndexRepository([{
            "code": "NIFTY IT", "name": "NIFTY IT", "category": "SECTORAL",
            "engine_isin": "INIDX0000180",
        }])
        market, recovery = FakeMarket(), FakeRecovery()
        service = IndexPipelineService(
            indices, market, FakeNse(), recovery, load_pattern_engine_configuration()
        )

        result = service.run(date(2016, 9, 11), date(2026, 9, 11), initiated_by="manual")

        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(2, result["rowsDownloaded"])
        self.assertEqual(("1D", "1W", "1M"), recovery.calls[0][1]["timeframes"])
        self.assertEqual("INDEX", recovery.calls[0][1]["instrument_type"])
        self.assertEqual(0, result["quadrantEvents"])

    def test_migration_keeps_indices_out_of_the_equity_universe(self):
        migration = (Path(__file__).parent / "migrations" / "035_create_index_analysis_universe.sql").read_text(encoding="utf-8")
        self.assertIn("'INDEX'", migration)
        self.assertIn("NIFTY 50", migration)
        tracking = (Path(__file__).parent / "migrations" / "036_track_index_quadrant_events.sql").read_text(encoding="utf-8")
        self.assertIn("index_quadrant_state", tracking)
        self.assertIn("index_quadrant_events", tracking)
        market_repository = (Path(__file__).parent / "repositories" / "market_data.py").read_text(encoding="utf-8")
        self.assertIn("WHERE series = 'EQ'", market_repository)


if __name__ == "__main__": unittest.main()
