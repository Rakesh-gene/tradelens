from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

from pattern_engine.enums import ImportJobType, ImportStatus
from repositories.market_data import PostgresMarketDataRepository


class RecordingCursor:
    def __init__(self, rows: list[tuple[object, ...]] | None = None, columns: list[str] | None = None) -> None:
        self.executed: list[tuple[str, object]] = []
        self.executed_many: list[tuple[str, list[object]]] = []
        self._rows = rows or []
        self.description = [SimpleNamespace(name=column) for column in (columns or [])]

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> None:
        self.executed.append((statement, parameters))

    def executemany(self, statement: str, parameters: list[object]) -> None:
        self.executed_many.append((statement, parameters))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self.cursor_instance = cursor
        self.commit_count = 0

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_count += 1


class MarketDataMigrationTestCase(unittest.TestCase):
    def test_phase_one_migrations_define_auditable_market_data_tables(self) -> None:
        migrations_path = Path(__file__).resolve().parent / "migrations"
        expected = {
            "006_create_market_import_tables.sql": [
                "CREATE TABLE IF NOT EXISTS market_import_runs",
                "CREATE TABLE IF NOT EXISTS security_import_checkpoints",
                "PRIMARY KEY (job_type, isin)",
            ],
            "007_create_market_data_tables.sql": [
                "CREATE TABLE IF NOT EXISTS nse_daily_bars_raw",
                "CREATE TABLE IF NOT EXISTS nse_corporate_actions",
                "CREATE TABLE IF NOT EXISTS adjusted_daily_bars",
                "PRIMARY KEY (isin, trading_date, adjustment_version)",
            ],
            "008_create_benchmark_sector_tables.sql": [
                "CREATE TABLE IF NOT EXISTS market_indices",
                "CREATE TABLE IF NOT EXISTS index_daily_bars",
                "CREATE TABLE IF NOT EXISTS security_sector_memberships",
                "CREATE TABLE IF NOT EXISTS index_constituent_memberships",
                "effective_from DATE NOT NULL",
            ],
            "009_create_technical_features.sql": [
                "CREATE TABLE IF NOT EXISTS technical_features",
                "PRIMARY KEY (isin, trading_date, feature_version)",
                "atr_14 NUMERIC",
                "secondary_metrics JSONB",
            ],
            "010_create_swings_and_zones.sql": [
                "CREATE TABLE IF NOT EXISTS swing_points",
                "CREATE TABLE IF NOT EXISTS price_zones",
                "breakout_buffer_pct NUMERIC NOT NULL",
                "source_swing_ids JSONB NOT NULL",
            ],
            "010_extend_feature_and_zone_fields.sql": [
                "ADD COLUMN IF NOT EXISTS volume_ratio_20 NUMERIC",
                "ADD COLUMN IF NOT EXISTS last_test_date DATE",
                "ADD COLUMN IF NOT EXISTS confirmation_date DATE",
            ],
        }

        for filename, required_fragments in expected.items():
            content = (migrations_path / filename).read_text(encoding="utf-8")
            for fragment in required_fragments:
                self.assertIn(fragment, content)


class PostgresMarketDataRepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.cursor = RecordingCursor()
        self.connection = RecordingConnection(self.cursor)
        self.repository = object.__new__(PostgresMarketDataRepository)
        self.repository._connect = lambda: self.connection

    def test_upsert_raw_bars_uses_natural_key_and_increments_revision(self) -> None:
        count = self.repository.upsert_raw_bars([
            {
                "isin": "INE000000001",
                "trading_date": date(2026, 9, 4),
                "open_price": Decimal("100"),
                "high_price": Decimal("105"),
                "low_price": Decimal("99"),
                "close_price": Decimal("104"),
                "volume": 1000,
                "nse_series": "EQ",
                "source_name": "NSE",
                "source_checksum": "abc123",
                "import_run_id": "00000000-0000-0000-0000-000000000001",
            }
        ])

        statement, parameters = self.cursor.executed_many[0]
        self.assertEqual(count, 1)
        self.assertIn("ON CONFLICT (isin, trading_date) DO UPDATE", statement)
        self.assertIn("raw_revision = nse_daily_bars_raw.raw_revision + 1", statement)
        self.assertEqual(parameters[0]["isin"], "INE000000001")
        self.assertIsNone(parameters[0]["deliverable_quantity"])
        self.assertEqual(self.connection.commit_count, 1)

    def test_swing_and_zone_upserts_are_versioned_and_zone_sources_are_json(self) -> None:
        self.repository.upsert_swing_points([{
            "id": "00000000-0000-0000-0000-000000000010", "isin": "INE000000001",
            "pivot_date": date(2026, 9, 1), "confirmation_date": date(2026, 9, 4),
            "swing_type": "HIGH", "price": Decimal("500"), "natr_14": Decimal("1.2"),
            "move_size_pct": Decimal("5"), "is_meaningful": True, "feature_version": "v1",
            "data_version": "adjusted-v1", "input_checksum": "swing-checksum",
        }])
        self.repository.upsert_price_zones([{
            "id": "00000000-0000-0000-0000-000000000011", "isin": "INE000000001",
            "zone_type": "RESISTANCE", "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 4),
            "median_price": Decimal("500"), "tolerance_pct": Decimal("0.75"),
            "breakout_buffer_pct": Decimal("0.30"), "dispersion_pct": Decimal("0.2"),
            "source_swing_ids": ("00000000-0000-0000-0000-000000000010",), "test_count": 1,
            "last_test_date": date(2026, 9, 1), "confirmation_date": date(2026, 9, 4),
            "feature_version": "v1", "data_version": "adjusted-v1", "input_checksum": "zone-checksum",
        }])

        swing_statement, _ = self.cursor.executed_many[0]
        zone_statement, zone_parameters = self.cursor.executed_many[1]
        self.assertIn("ON CONFLICT (isin, pivot_date, swing_type, feature_version)", swing_statement)
        self.assertIn("ON CONFLICT (isin, zone_type, start_date, end_date, feature_version)", zone_statement)
        self.assertEqual(zone_parameters[0]["source_swing_ids"], '["00000000-0000-0000-0000-000000000010"]')

    def test_history_chunk_and_checkpoint_commit_in_one_transaction(self) -> None:
        bars = [{
            "isin": "INE000000001", "trading_date": date(2026, 9, 4),
            "open_price": Decimal("100"), "high_price": Decimal("105"),
            "low_price": Decimal("99"), "close_price": Decimal("104"),
            "volume": 1000, "nse_series": "EQ", "source_name": "NSE",
            "source_checksum": "abc123",
        }]
        checkpoint = {
            "job_type": ImportJobType.HISTORY_BACKFILL,
            "isin": "INE000000001",
            "last_attempted_from_date": date(2026, 9, 4),
            "last_attempted_to_date": date(2026, 9, 4),
            "status": ImportStatus.COMPLETED,
        }

        count = self.repository.persist_history_chunk(bars, checkpoint)

        self.assertEqual(count, 1)
        self.assertEqual(len(self.cursor.executed_many), 1)
        self.assertEqual(len(self.cursor.executed), 1)
        self.assertIn("INSERT INTO security_import_checkpoints", self.cursor.executed[0][0])
        self.assertEqual(self.connection.commit_count, 1)

    def test_upsert_actions_serializes_payload_and_uses_source_event_key(self) -> None:
        self.repository.upsert_corporate_actions([
            {
                "source_event_key": "NSE:split:1",
                "isin": "INE000000001",
                "symbol": "EXAMPLE",
                "action_type": "SPLIT",
                "ex_date": date(2026, 9, 4),
                "raw_payload": {"ratio": "2:1"},
                "source_checksum": "def456",
            }
        ])

        statement, parameters = self.cursor.executed_many[0]
        self.assertIn("ON CONFLICT (source_event_key) DO UPDATE", statement)
        self.assertEqual(parameters[0]["raw_payload"], '{"ratio": "2:1"}')
        self.assertEqual(parameters[0]["source_event_key"], "NSE:split:1")

    def test_create_import_run_records_versioned_configuration(self) -> None:
        with patch("repositories.market_data.uuid4", return_value="00000000-0000-0000-0000-000000000001"):
            run_id = self.repository.create_import_run(
                ImportJobType.HISTORY_BACKFILL,
                "manual",
                requested_from_date=date(2016, 1, 1),
                requested_to_date=date(2026, 1, 1),
                configuration={"version": "v1"},
                securities_total=10,
            )

        statement, parameters = self.cursor.executed[0]
        self.assertEqual(run_id, "00000000-0000-0000-0000-000000000001")
        self.assertIn("INSERT INTO market_import_runs", statement)
        self.assertEqual(parameters[1], "HISTORY_BACKFILL")
        self.assertEqual(parameters[4], '{"version": "v1"}')
        self.assertEqual(parameters[5], "PENDING")
        self.assertEqual(self.connection.commit_count, 1)

    def test_create_import_run_serializes_immutable_configuration_as_json_object(self) -> None:
        immutable_configuration = MappingProxyType(
            {"engine": MappingProxyType({"version": "v1"})}
        )

        self.repository.create_import_run(
            ImportJobType.DAILY_DELTA,
            "scheduler",
            configuration=immutable_configuration,
        )

        _, parameters = self.cursor.executed[0]
        self.assertEqual(parameters[4], '{"engine": {"version": "v1"}}')

    def test_checkpoint_preserves_import_history_with_parameterized_upsert(self) -> None:
        self.repository.upsert_import_checkpoint(
            {
                "job_type": ImportJobType.HISTORY_BACKFILL,
                "isin": "INE000000001",
                "earliest_successful_trading_date": date(2016, 1, 1),
                "latest_successful_trading_date": date(2016, 1, 31),
                "last_attempted_from_date": date(2016, 1, 1),
                "last_attempted_to_date": date(2016, 1, 31),
                "status": ImportStatus.COMPLETED,
                "last_successful_run_id": "00000000-0000-0000-0000-000000000001",
            }
        )

        statement, parameters = self.cursor.executed[0]
        self.assertIn("ON CONFLICT (job_type, isin) DO UPDATE", statement)
        self.assertIn("LEAST(", statement)
        self.assertIn("GREATEST(", statement)
        self.assertEqual(parameters["job_type"], "HISTORY_BACKFILL")
        self.assertEqual(parameters["status"], "COMPLETED")

    def test_loading_bars_is_bounded_and_returns_named_columns(self) -> None:
        self.cursor = RecordingCursor(
            rows=[("INE000000001", date(2026, 9, 4), Decimal("104"))],
            columns=["isin", "trading_date", "close_price"],
        )
        self.connection = RecordingConnection(self.cursor)
        self.repository._connect = lambda: self.connection

        bars = self.repository.load_raw_bars(
            "INE000000001", date(2026, 9, 1), date(2026, 9, 4)
        )

        statement, parameters = self.cursor.executed[0]
        self.assertIn("trading_date >= %s AND trading_date <= %s", statement)
        self.assertEqual(parameters, ("INE000000001", date(2026, 9, 1), date(2026, 9, 4)))
        self.assertEqual(bars, [{"isin": "INE000000001", "trading_date": date(2026, 9, 4), "close_price": Decimal("104")}])

    def test_loading_corporate_actions_supports_point_in_time_filter(self) -> None:
        self.cursor = RecordingCursor(
            rows=[("NSE:1", "INE000000001", date(2026, 9, 4))],
            columns=["source_event_key", "isin", "ex_date"],
        )
        self.connection = RecordingConnection(self.cursor)
        self.repository._connect = lambda: self.connection

        actions = self.repository.load_corporate_actions(
            "INE000000001", date(2026, 1, 1), date(2026, 12, 31), as_of=datetime(2026, 9, 5)
        )

        statement, parameters = self.cursor.executed[0]
        self.assertIn("imported_at <= %s", statement)
        self.assertEqual(parameters[0:3], ("INE000000001", date(2026, 1, 1), date(2026, 12, 31)))
        self.assertEqual(len(actions), 1)


if __name__ == "__main__":
    unittest.main()
