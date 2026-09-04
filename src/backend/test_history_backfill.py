from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from data_pipeline.history_backfill import BackfillRequest, HistoryBackfillService
from data_pipeline.models import NseCorporateActionRecord, NseEquityHistoryRecord, freeze_json_value
from pattern_engine.enums import ImportJobType, ImportStatus


class FakeRepository:
    def __init__(self) -> None:
        self.securities = [
            {"isin": "INE000000001", "symbol": "EXAMPLE", "series": "EQ", "listed_on": date(2020, 1, 1)},
            {"isin": "INE000000002", "symbol": "PREF", "series": "P1", "listed_on": date(2020, 1, 1)},
            {"isin": "INE000000003", "symbol": "BROKEN", "series": "EQ", "listed_on": date(2020, 1, 1)},
        ]
        self.date_ranges: dict[str, tuple[date | None, date | None]] = {}
        self.checkpoints: dict[tuple[ImportJobType, str], dict[str, object]] = {}
        self.runs: list[tuple[str, object]] = []
        self.raw_bars: list[dict[str, object]] = []
        self.actions: list[dict[str, object]] = []

    def list_eligible_securities(self): return self.securities
    def get_raw_bar_date_range(self, isin): return self.date_ranges.get(isin, (None, None))
    def get_import_checkpoint(self, job_type, isin): return self.checkpoints.get((job_type, isin))
    def create_import_run(self, *_args, **_kwargs): return "run-1"
    def update_import_run(self, run_id, status, **kwargs): self.runs.append((run_id, status, kwargs))
    def upsert_raw_bars(self, bars): self.raw_bars.extend(bars); return len(bars)
    def persist_history_chunk(self, bars, checkpoint):
        self.raw_bars.extend(bars)
        self.upsert_import_checkpoint(checkpoint)
        return len(bars)
    def upsert_corporate_actions(self, actions): self.actions.extend(actions); return len(actions)
    def upsert_import_checkpoint(self, checkpoint): self.checkpoints[(checkpoint["job_type"], checkpoint["isin"])] = dict(checkpoint)


class FakeNseClient:
    def __init__(self, fail_symbol: str | None = None) -> None:
        self.fail_symbol = fail_symbol
        self.history_calls: list[tuple[str, date, date]] = []
        self.action_calls: list[tuple[str, date, date]] = []

    def fetch_equity_history(self, symbol, from_date, to_date):
        self.history_calls.append((symbol, from_date, to_date))
        if symbol == self.fail_symbol:
            raise RuntimeError("NSE temporarily unavailable")
        return [self._bar(symbol, from_date)]

    def fetch_corporate_actions(self, symbol, from_date, to_date):
        self.action_calls.append((symbol, from_date, to_date))
        return [NseCorporateActionRecord(
            source_event_key=f"NSE:{symbol}:action",
            symbol=symbol,
            source_isin="INE000000001" if symbol == "EXAMPLE" else "INE000000003",
            action_type="DIVIDEND",
            ex_date=from_date,
            record_date=None,
            announcement_date=None,
            numerator=None,
            denominator=None,
            cash_value=Decimal("1"),
            currency="INR",
            raw_description="Dividend Rs. 1",
            source_checksum="action-checksum",
            source_payload=freeze_json_value({"symbol": symbol}),
        )]

    @staticmethod
    def _bar(symbol, trading_date):
        isin = "INE000000001" if symbol == "EXAMPLE" else "INE000000003"
        return NseEquityHistoryRecord(
            symbol=symbol, source_isin=isin, series="EQ", trading_date=trading_date,
            open_price=Decimal("100"), high_price=Decimal("105"), low_price=Decimal("99"),
            close_price=Decimal("104"), volume=1000, deliverable_quantity=None,
            delivery_percentage=None, source_checksum=f"{symbol}-{trading_date}",
            source_payload=freeze_json_value({"symbol": symbol, "date": trading_date.isoformat()}),
        )


class HistoryBackfillServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRepository()
        self.client = FakeNseClient(fail_symbol="BROKEN")
        self.service = HistoryBackfillService(self.repository, self.client, today=lambda: date(2026, 9, 4))

    def test_dry_run_plans_listing_bounded_one_year_chunks_without_writes_or_http(self) -> None:
        result = self.service.run(BackfillRequest(
            from_date=date(2019, 1, 1), to_date=date(2022, 1, 2), dry_run=True
        ))

        self.assertIsNone(result.run_id)
        self.assertEqual([item.isin for item in result.securities], ["INE000000001", "INE000000003"])
        self.assertEqual(result.securities[0].requested_from_date, date(2020, 1, 1))
        self.assertEqual(result.securities[0].chunks, [
            (date(2020, 1, 1), date(2020, 12, 31)),
            (date(2021, 1, 1), date(2021, 12, 31)),
            (date(2022, 1, 1), date(2022, 1, 2)),
        ])
        self.assertEqual(self.client.history_calls, [])
        self.assertEqual(self.repository.runs, [])

    def test_import_continues_after_one_security_failure_and_records_checkpoint(self) -> None:
        result = self.service.run(BackfillRequest(from_date=date(2026, 9, 4), to_date=date(2026, 9, 4)))

        self.assertEqual(result.status, ImportStatus.PARTIAL)
        self.assertEqual(result.securities[0].rows_inserted, 1)
        self.assertIsNone(result.securities[0].error)
        self.assertIn("NSE temporarily unavailable", result.securities[1].error or "")
        failed_checkpoint = self.repository.checkpoints[(ImportJobType.HISTORY_BACKFILL, "INE000000003")]
        self.assertEqual(failed_checkpoint["status"], ImportStatus.FAILED)
        self.assertEqual(len(self.repository.raw_bars), 1)
        self.assertEqual(len(self.repository.actions), 1)

    def test_completed_checkpoint_skips_download_for_already_covered_range(self) -> None:
        self.repository.checkpoints[(ImportJobType.HISTORY_BACKFILL, "INE000000001")] = {
            "status": ImportStatus.COMPLETED.value,
            "last_attempted_from_date": date(2026, 1, 1),
            "last_attempted_to_date": date(2026, 12, 31),
        }
        self.repository.checkpoints[(ImportJobType.CORPORATE_ACTION_BACKFILL, "INE000000001")] = {
            "status": ImportStatus.COMPLETED.value,
            "last_attempted_from_date": date(2026, 1, 1),
            "last_attempted_to_date": date(2026, 12, 31),
        }

        result = self.service.run(BackfillRequest(
            from_date=date(2026, 9, 4), to_date=date(2026, 9, 4), symbol="EXAMPLE"
        ))

        self.assertEqual(result.status, ImportStatus.COMPLETED)
        self.assertEqual(self.client.history_calls, [])
        self.assertEqual(self.client.action_calls, [])
        self.assertEqual(result.securities[0].chunks, [])

    def test_retry_failed_selects_only_failed_security_checkpoints(self) -> None:
        self.repository.checkpoints[(ImportJobType.HISTORY_BACKFILL, "INE000000003")] = {
            "status": ImportStatus.FAILED.value,
            "retry_count": 1,
        }

        result = self.service.run(BackfillRequest(
            from_date=date(2026, 9, 4),
            to_date=date(2026, 9, 4),
            retry_failed=True,
            dry_run=True,
        ))

        self.assertEqual([item.isin for item in result.securities], ["INE000000003"])


if __name__ == "__main__":
    unittest.main()
