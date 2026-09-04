from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from data_pipeline.daily_delta import DailyDeltaRequest, DailyDeltaService
from data_pipeline.models import NseCorporateActionRecord, NseEquityHistoryRecord, freeze_json_value
from data_pipeline.normalization import parse_eod_report
from pattern_engine.enums import ImportStatus


LATEST = date(2026, 9, 4)


class DeltaRepository:
    def __init__(self):
        self.securities = [{"isin": "INE000000001", "symbol": "EXAMPLE", "series": "EQ", "listed_on": date(2020, 1, 1)}]
        self.bars = [{"isin": "INE000000001", "trading_date": LATEST, "source_checksum": "old"}]
        self.checkpoints = {}
        self.run_updates = []
        self.committed = []
        self.actions = []

    def list_eligible_securities(self): return self.securities
    def get_raw_bar_date_range(self, isin): return (LATEST, LATEST)
    def load_raw_bars(self, isin, start, end): return self.bars
    def get_import_checkpoint(self, job_type, isin): return self.checkpoints.get((job_type, isin))
    def load_corporate_actions(self, isin, start, end, *, as_of=None): return self.actions
    def create_import_run(self, *args, **kwargs): return "daily-run"
    def update_import_run(self, *args, **kwargs): self.run_updates.append((args, kwargs))
    def persist_history_chunk(self, bars, checkpoint):
        self.bars.extend(bars); self.checkpoints[(checkpoint["job_type"], checkpoint["isin"])] = checkpoint
        self.committed.append(checkpoint); return len(bars)
    def upsert_corporate_actions(self, actions): self.actions = list(actions); return len(actions)
    def upsert_import_checkpoint(self, checkpoint): self.checkpoints[(checkpoint["job_type"], checkpoint["isin"])] = checkpoint


class DeltaClient:
    def __init__(self, checksum="new"):
        self.checksum = checksum
        self.history_calls = []
        self.action_calls = []

    def fetch_equity_history(self, symbol, start, end):
        self.history_calls.append((symbol, start, end))
        return [self.bar()]

    def bar(self):
        return NseEquityHistoryRecord(
            symbol="EXAMPLE", source_isin="INE000000001", series="EQ", trading_date=LATEST,
            open_price=Decimal("100"), high_price=Decimal("105"), low_price=Decimal("99"),
            close_price=Decimal("104"), volume=1000, deliverable_quantity=None,
            delivery_percentage=None, source_checksum=self.checksum,
            source_payload=freeze_json_value({"checksum": self.checksum}),
        )

    def fetch_corporate_actions(self, symbol, start, end):
        self.action_calls.append((symbol, start, end)); return []


class DailyDeltaServiceTestCase(unittest.TestCase):
    def _resolver(self, as_of, securities):
        return LATEST, {}

    def test_corrected_bar_is_detected_and_callback_runs_after_commit(self):
        repository = DeltaRepository()
        client = DeltaClient("corrected")
        commits = []
        result = DailyDeltaService(
            repository, client, session_resolver=self._resolver,
            on_source_commit=lambda isin, start, end: commits.append((isin, start, end)),
            today=lambda: LATEST,
        ).run(DailyDeltaRequest(as_of=LATEST, repair_sessions=10))

        self.assertEqual(result.status, ImportStatus.COMPLETED)
        self.assertEqual(result.securities[0].changed_from_date, LATEST)
        self.assertEqual(commits, [("INE000000001", LATEST, LATEST)])
        self.assertTrue(repository.committed)

    def test_second_run_is_idempotent_for_same_source_checksum(self):
        repository = DeltaRepository()
        client = DeltaClient("old")
        result = DailyDeltaService(repository, client, session_resolver=self._resolver, today=lambda: LATEST).run(
            DailyDeltaRequest(as_of=LATEST, repair_sessions=10)
        )

        self.assertEqual(result.status, ImportStatus.COMPLETED)
        self.assertIsNone(result.securities[0].changed_from_date)
        self.assertEqual(result.securities[0].rows_inserted, 0)
        self.assertEqual(result.securities[0].rows_updated, 0)

    def test_new_listing_starts_at_listing_date_and_is_eligible(self):
        repository = DeltaRepository()
        repository.bars = []
        repository.securities[0]["listed_on"] = LATEST
        client = DeltaClient("new-listing")
        result = DailyDeltaService(repository, client, session_resolver=lambda _as_of, _securities: (LATEST, {"INE000000001": client.bar()}), today=lambda: LATEST).run(
            DailyDeltaRequest(as_of=LATEST, repair_sessions=10)
        )

        self.assertEqual(result.securities[0].from_date, LATEST)
        self.assertEqual(client.history_calls, [])  # bulk resolver represents the published EOD row

    def test_repair_window_uses_stored_trading_sessions(self):
        repository = DeltaRepository()
        sessions = sorted(
            LATEST - timedelta(days=offset)
            for offset in range(25)
            if (LATEST - timedelta(days=offset)).weekday() < 5
        )
        repository.bars = [
            {"isin": "INE000000001", "trading_date": session, "source_checksum": str(session)}
            for session in sessions
        ]
        service = DailyDeltaService(repository, DeltaClient(), session_resolver=self._resolver, today=lambda: LATEST)

        result = service.run(DailyDeltaRequest(as_of=LATEST, repair_sessions=10, dry_run=True))

        self.assertEqual(result.securities[0].from_date, sessions[-11])

    def test_eod_parser_keeps_valid_rows_and_leaves_rejected_rows_for_fallback(self):
        report = (
            b"TradDt,ISIN,OpnPric,HghPric,LwPric,ClsPric,TtlTrdQty\n"
            b"04-Sep-2026,INE000000001,100,105,99,104,1000\n"
            b"04-Sep-2026,INE000000002,bad,105,99,104,1000\n"
        )
        securities = {
            "INE000000001": {"symbol": "EXAMPLE"},
            "INE000000002": {"symbol": "REJECTED"},
        }

        bars = parse_eod_report(report, securities)

        self.assertEqual(list(bars), ["INE000000001"])
        self.assertEqual(bars["INE000000001"].trading_date, LATEST)


if __name__ == "__main__":
    unittest.main()
