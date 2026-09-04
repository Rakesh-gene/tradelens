"""Bounded PostgreSQL persistence for imported and adjusted market data."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Mapping, Protocol, Sequence
from uuid import uuid4

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional at test time
    psycopg = None

from pattern_engine.enums import ImportJobType, ImportStatus
from pattern_engine.models import serialize_value
from repositories.migrations import MigrationRunner


class MarketDataRepository(Protocol):
    """Persistence required by import, adjustment, and incremental scan jobs."""

    def list_eligible_securities(self) -> list[dict[str, object]]:
        ...

    def get_raw_bar_date_range(self, isin: str) -> tuple[date | None, date | None]:
        ...

    def upsert_raw_bars(self, bars: Sequence[Mapping[str, object]]) -> int:
        ...

    def persist_history_chunk(
        self, bars: Sequence[Mapping[str, object]], checkpoint: Mapping[str, object]
    ) -> int:
        ...

    def upsert_corporate_actions(self, actions: Sequence[Mapping[str, object]]) -> int:
        ...

    def load_corporate_actions(
        self, isin: str, from_date: date, to_date: date, *, as_of: datetime | None = None
    ) -> list[dict[str, object]]:
        ...

    def load_raw_bars(self, isin: str, from_date: date, to_date: date) -> list[dict[str, object]]:
        ...

    def load_adjusted_bars(
        self, isin: str, from_date: date, to_date: date, adjustment_version: str
    ) -> list[dict[str, object]]:
        ...

    def upsert_adjusted_bars(self, bars: Sequence[Mapping[str, object]]) -> int:
        ...

    def load_technical_features(self, isin: str, from_date: date, to_date: date, feature_version: str) -> list[dict[str, object]]:
        ...

    def upsert_technical_features(self, features: Sequence[Mapping[str, object]]) -> int:
        ...

    def load_swing_points(
        self, isin: str, from_date: date, to_date: date, feature_version: str, *, as_of: date | None = None
    ) -> list[dict[str, object]]:
        ...

    def upsert_swing_points(self, swings: Sequence[Mapping[str, object]]) -> int:
        ...

    def load_price_zones(
        self, isin: str, from_date: date, to_date: date, feature_version: str, *, as_of: date | None = None
    ) -> list[dict[str, object]]:
        ...

    def upsert_price_zones(self, zones: Sequence[Mapping[str, object]]) -> int:
        ...

    def create_import_run(
        self,
        job_type: ImportJobType,
        initiated_by: str,
        *,
        requested_from_date: date | None = None,
        requested_to_date: date | None = None,
        configuration: Mapping[str, object] | None = None,
        securities_total: int = 0,
    ) -> str:
        ...

    def mark_interrupted_import_runs(self, job_type: ImportJobType) -> int:
        ...

    def update_import_run(
        self,
        run_id: str,
        status: ImportStatus,
        *,
        securities_total: int | None = None,
        securities_completed: int | None = None,
        securities_failed: int | None = None,
        rows_downloaded: int | None = None,
        rows_inserted: int | None = None,
        rows_updated: int | None = None,
        rows_rejected: int | None = None,
        error_summary: str | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        ...

    def upsert_import_checkpoint(self, checkpoint: Mapping[str, object]) -> None:
        ...

    def get_import_checkpoint(self, job_type: ImportJobType, isin: str) -> dict[str, object] | None:
        ...

    def list_affected_security_dates(self, run_id: str) -> list[dict[str, object]]:
        ...


class PostgresMarketDataRepository:
    """PostgreSQL implementation that applies the full ordered migration set."""

    def __init__(self, dsn: str, *, apply_migrations: bool = True) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        if apply_migrations:
            self._apply_migrations()

    def _connect(self):
        return psycopg.connect(self._dsn)

    def _apply_migrations(self) -> None:
        migrations_path = Path(__file__).resolve().parents[1] / "migrations"
        MigrationRunner(self._connect, migrations_path).apply()

    def list_eligible_securities(self) -> list[dict[str, object]]:
        statement = """
            SELECT isin, symbol, company_name, series, listed_on
            FROM nse_equities
            ORDER BY isin
        """
        return self._fetch_all(statement, ())

    def get_raw_bar_date_range(self, isin: str) -> tuple[date | None, date | None]:
        statement = """
            SELECT MIN(trading_date), MAX(trading_date)
            FROM nse_daily_bars_raw
            WHERE isin = %s
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (isin,))
                row = cursor.fetchone()
        return (row[0], row[1]) if row is not None else (None, None)

    def upsert_raw_bars(self, bars: Sequence[Mapping[str, object]]) -> int:
        if not bars:
            return 0
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._upsert_raw_bars_with_cursor(cursor, bars)
            connection.commit()
        return len(bars)

    def persist_history_chunk(
        self, bars: Sequence[Mapping[str, object]], checkpoint: Mapping[str, object]
    ) -> int:
        """Commit a validated source chunk and its resumability checkpoint atomically."""

        with self._connect() as connection:
            with connection.cursor() as cursor:
                if bars:
                    self._upsert_raw_bars_with_cursor(cursor, bars)
                self._upsert_checkpoint_with_cursor(cursor, checkpoint)
            connection.commit()
        return len(bars)

    def upsert_corporate_actions(self, actions: Sequence[Mapping[str, object]]) -> int:
        if not actions:
            return 0
        statement = """
            INSERT INTO nse_corporate_actions (
                source_event_key, isin, symbol, action_type, ex_date, record_date,
                announcement_date, numerator, denominator, cash_value, currency,
                raw_description, raw_payload, source_checksum, import_run_id
            ) VALUES (
                %(source_event_key)s, %(isin)s, %(symbol)s, %(action_type)s, %(ex_date)s,
                %(record_date)s, %(announcement_date)s, %(numerator)s, %(denominator)s,
                %(cash_value)s, %(currency)s, %(raw_description)s,
                %(raw_payload)s::jsonb, %(source_checksum)s, %(import_run_id)s
            )
            ON CONFLICT (source_event_key) DO UPDATE SET
                isin = EXCLUDED.isin,
                symbol = EXCLUDED.symbol,
                action_type = EXCLUDED.action_type,
                ex_date = EXCLUDED.ex_date,
                record_date = EXCLUDED.record_date,
                announcement_date = EXCLUDED.announcement_date,
                numerator = EXCLUDED.numerator,
                denominator = EXCLUDED.denominator,
                cash_value = EXCLUDED.cash_value,
                currency = EXCLUDED.currency,
                raw_description = EXCLUDED.raw_description,
                raw_payload = EXCLUDED.raw_payload,
                source_checksum = EXCLUDED.source_checksum,
                import_run_id = EXCLUDED.import_run_id,
                updated_at = NOW()
            WHERE nse_corporate_actions.source_checksum IS DISTINCT FROM EXCLUDED.source_checksum
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(statement, [self._corporate_action_parameters(action) for action in actions])
            connection.commit()
        return len(actions)

    def load_raw_bars(self, isin: str, from_date: date, to_date: date) -> list[dict[str, object]]:
        return self._load_bars("nse_daily_bars_raw", isin, from_date, to_date)

    def load_corporate_actions(
        self, isin: str, from_date: date, to_date: date, *, as_of: datetime | None = None
    ) -> list[dict[str, object]]:
        statement = """
            SELECT source_event_key, isin, symbol, action_type, ex_date, record_date,
                   announcement_date, numerator, denominator, cash_value, currency,
                   raw_description, raw_payload, source_checksum, import_run_id,
                   imported_at, updated_at
            FROM nse_corporate_actions
            WHERE isin = %s AND ex_date >= %s AND ex_date <= %s
              AND (%s IS NULL OR imported_at <= %s)
            ORDER BY ex_date, source_event_key
        """
        return self._fetch_all(statement, (isin, from_date, to_date, as_of, as_of))

    def load_adjusted_bars(
        self, isin: str, from_date: date, to_date: date, adjustment_version: str
    ) -> list[dict[str, object]]:
        statement = """
            SELECT adjusted.*, raw.deliverable_quantity, raw.delivery_percentage
            FROM adjusted_daily_bars AS adjusted
            LEFT JOIN nse_daily_bars_raw AS raw
              ON raw.isin = adjusted.isin AND raw.trading_date = adjusted.trading_date
            WHERE adjusted.isin = %s
              AND adjusted.trading_date >= %s
              AND adjusted.trading_date <= %s
              AND adjusted.adjustment_version = %s
            ORDER BY adjusted.trading_date
        """
        return self._fetch_all(statement, (isin, from_date, to_date, adjustment_version))

    def upsert_adjusted_bars(self, bars: Sequence[Mapping[str, object]]) -> int:
        if not bars:
            return 0
        statement = """
            INSERT INTO adjusted_daily_bars (
                isin, trading_date, adjustment_version, open_price, high_price,
                low_price, close_price, volume, price_adjustment_factor,
                volume_adjustment_factor, adjustment_source, source_revision,
                action_set_checksum
            ) VALUES (
                %(isin)s, %(trading_date)s, %(adjustment_version)s, %(open_price)s,
                %(high_price)s, %(low_price)s, %(close_price)s, %(volume)s,
                %(price_adjustment_factor)s, %(volume_adjustment_factor)s,
                %(adjustment_source)s, %(source_revision)s, %(action_set_checksum)s
            )
            ON CONFLICT (isin, trading_date, adjustment_version) DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                price_adjustment_factor = EXCLUDED.price_adjustment_factor,
                volume_adjustment_factor = EXCLUDED.volume_adjustment_factor,
                adjustment_source = EXCLUDED.adjustment_source,
                source_revision = EXCLUDED.source_revision,
                action_set_checksum = EXCLUDED.action_set_checksum,
                generated_at = NOW()
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(statement, list(bars))
            connection.commit()
        return len(bars)

    def load_technical_features(self, isin: str, from_date: date, to_date: date, feature_version: str) -> list[dict[str, object]]:
        return self._fetch_all("""
            SELECT * FROM technical_features WHERE isin = %s AND trading_date >= %s
              AND trading_date <= %s AND feature_version = %s ORDER BY trading_date
        """, (isin, from_date, to_date, feature_version))

    def upsert_technical_features(self, features: Sequence[Mapping[str, object]]) -> int:
        if not features:
            return 0
        columns = (
            "isin,trading_date,feature_version,data_version,true_range,atr_5,atr_10,atr_14,atr_20,atr_50,natr_14,"
            "ema_10,ema_20,sma_50,sma_100,sma_200,ema_20_slope,sma_50_slope,sma_200_slope,"
            "range_5,range_10,range_20,range_50,median_volume_5,median_volume_10,median_volume_20,median_volume_50,"
            "volume_ratio_5_to_50,volume_contraction_ratio,close_location_value,high_52_week,low_52_week,"
            "range_position_52_week,distance_to_52_week_high_pct,all_time_high,distance_to_all_time_high_pct,"
            "return_1_month,return_3_month,return_6_month,return_12_month,relative_strength_1m,relative_strength_3m,"
            "relative_strength_6m,relative_strength_12m,relative_strength_percentile,relative_strength_composite,"
            "delivery_percentage,median_delivery_percentage_5,median_delivery_percentage_20,delivery_expansion_ratio,input_checksum,secondary_metrics"
        ).split(",")
        columns[-2:-2] = ["volume_ratio_20", "distance_to_ema_20_pct", "distance_to_sma_50_pct", "distance_to_sma_200_pct", "deliverable_volume", "median_traded_value_20"]
        placeholders = ", ".join(f"%({column})s" + ("::jsonb" if column == "secondary_metrics" else "") for column in columns)
        updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column not in {"isin", "trading_date", "feature_version"})
        statement = f"INSERT INTO technical_features ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT (isin, trading_date, feature_version) DO UPDATE SET {updates}, generated_at = NOW()"
        parameters = []
        for feature in features:
            values = {column: feature.get(column) for column in columns}
            values["secondary_metrics"] = json.dumps(serialize_value(values["secondary_metrics"] or {}), sort_keys=True)
            parameters.append(values)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(statement, parameters)
            connection.commit()
        return len(features)

    def load_swing_points(
        self, isin: str, from_date: date, to_date: date, feature_version: str, *, as_of: date | None = None
    ) -> list[dict[str, object]]:
        return self._fetch_all("""
            SELECT * FROM swing_points WHERE isin = %s AND pivot_date >= %s AND pivot_date <= %s
              AND feature_version = %s AND (%s IS NULL OR confirmation_date <= %s)
            ORDER BY pivot_date, swing_type
        """, (isin, from_date, to_date, feature_version, as_of, as_of))

    def upsert_swing_points(self, swings: Sequence[Mapping[str, object]]) -> int:
        if not swings:
            return 0
        statement = """
            INSERT INTO swing_points (id, isin, pivot_date, confirmation_date, swing_type, price,
                natr_14, move_size_pct, is_meaningful, feature_version, data_version, input_checksum)
            VALUES (%(id)s, %(isin)s, %(pivot_date)s, %(confirmation_date)s, %(swing_type)s, %(price)s,
                %(natr_14)s, %(move_size_pct)s, %(is_meaningful)s, %(feature_version)s, %(data_version)s, %(input_checksum)s)
            ON CONFLICT (isin, pivot_date, swing_type, feature_version) DO UPDATE SET
                confirmation_date = EXCLUDED.confirmation_date, price = EXCLUDED.price, natr_14 = EXCLUDED.natr_14,
                move_size_pct = EXCLUDED.move_size_pct, is_meaningful = EXCLUDED.is_meaningful,
                data_version = EXCLUDED.data_version, input_checksum = EXCLUDED.input_checksum
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(statement, list(swings))
            connection.commit()
        return len(swings)

    def load_price_zones(
        self, isin: str, from_date: date, to_date: date, feature_version: str, *, as_of: date | None = None
    ) -> list[dict[str, object]]:
        return self._fetch_all("""
            SELECT * FROM price_zones WHERE isin = %s AND last_test_date >= %s AND last_test_date <= %s
              AND feature_version = %s AND (%s IS NULL OR confirmation_date <= %s)
            ORDER BY zone_type, median_price, start_date
        """, (isin, from_date, to_date, feature_version, as_of, as_of))

    def upsert_price_zones(self, zones: Sequence[Mapping[str, object]]) -> int:
        if not zones:
            return 0
        statement = """
            INSERT INTO price_zones (id, isin, zone_type, start_date, end_date, median_price,
                tolerance_pct, breakout_buffer_pct, dispersion_pct, source_swing_ids, test_count, last_test_date, confirmation_date,
                feature_version, data_version, input_checksum)
            VALUES (%(id)s, %(isin)s, %(zone_type)s, %(start_date)s, %(end_date)s, %(median_price)s,
                %(tolerance_pct)s, %(breakout_buffer_pct)s, %(dispersion_pct)s, %(source_swing_ids)s::jsonb, %(test_count)s, %(last_test_date)s, %(confirmation_date)s,
                %(feature_version)s, %(data_version)s, %(input_checksum)s)
            ON CONFLICT (isin, zone_type, start_date, end_date, feature_version) DO UPDATE SET
                median_price = EXCLUDED.median_price, tolerance_pct = EXCLUDED.tolerance_pct,
                breakout_buffer_pct = EXCLUDED.breakout_buffer_pct, dispersion_pct = EXCLUDED.dispersion_pct,
                source_swing_ids = EXCLUDED.source_swing_ids, test_count = EXCLUDED.test_count,
                last_test_date = EXCLUDED.last_test_date, confirmation_date = EXCLUDED.confirmation_date,
                data_version = EXCLUDED.data_version, input_checksum = EXCLUDED.input_checksum
        """
        parameters = []
        for zone in zones:
            values = dict(zone)
            values["source_swing_ids"] = json.dumps(serialize_value(values.get("source_swing_ids", [])), sort_keys=True)
            parameters.append(values)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(statement, parameters)
            connection.commit()
        return len(zones)

    def create_import_run(
        self,
        job_type: ImportJobType,
        initiated_by: str,
        *,
        requested_from_date: date | None = None,
        requested_to_date: date | None = None,
        configuration: Mapping[str, object] | None = None,
        securities_total: int = 0,
    ) -> str:
        run_id = str(uuid4())
        statement = """
            INSERT INTO market_import_runs (
                id, job_type, requested_from_date, requested_to_date, configuration,
                status, securities_total, initiated_by
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    statement,
                    (
                        run_id,
                        job_type.value,
                        requested_from_date,
                        requested_to_date,
                        json.dumps(serialize_value(configuration or {}), sort_keys=True),
                        ImportStatus.PENDING.value,
                        securities_total,
                        initiated_by,
                    ),
                )
            connection.commit()
        return run_id

    def mark_interrupted_import_runs(self, job_type: ImportJobType) -> int:
        """Close abandoned jobs before a deliberate recovery invocation resumes checkpoints."""

        statement = """
            UPDATE market_import_runs
            SET status = 'FAILED', finished_at = NOW(),
                error_summary = COALESCE(error_summary, 'Interrupted before completion; recovery requested')
            WHERE job_type = %s AND status = 'RUNNING'
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (job_type.value,))
                count = cursor.rowcount if getattr(cursor, "rowcount", None) is not None else 0
            connection.commit()
        return int(count)

    def update_import_run(
        self,
        run_id: str,
        status: ImportStatus,
        *,
        securities_total: int | None = None,
        securities_completed: int | None = None,
        securities_failed: int | None = None,
        rows_downloaded: int | None = None,
        rows_inserted: int | None = None,
        rows_updated: int | None = None,
        rows_rejected: int | None = None,
        error_summary: str | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        statement = """
            UPDATE market_import_runs
            SET status = %(status)s,
                finished_at = CASE
                    WHEN %(finished_at)s IS NOT NULL THEN %(finished_at)s
                    WHEN %(status)s IN ('COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED') THEN NOW()
                    ELSE finished_at
                END,
                securities_total = COALESCE(%(securities_total)s, securities_total),
                securities_completed = COALESCE(%(securities_completed)s, securities_completed),
                securities_failed = COALESCE(%(securities_failed)s, securities_failed),
                rows_downloaded = COALESCE(%(rows_downloaded)s, rows_downloaded),
                rows_inserted = COALESCE(%(rows_inserted)s, rows_inserted),
                rows_updated = COALESCE(%(rows_updated)s, rows_updated),
                rows_rejected = COALESCE(%(rows_rejected)s, rows_rejected),
                error_summary = COALESCE(%(error_summary)s, error_summary)
            WHERE id = %(run_id)s
        """
        parameters = {
            "run_id": run_id,
            "status": status.value,
            "finished_at": finished_at,
            "securities_total": securities_total,
            "securities_completed": securities_completed,
            "securities_failed": securities_failed,
            "rows_downloaded": rows_downloaded,
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "rows_rejected": rows_rejected,
            "error_summary": error_summary,
        }
        self._execute(statement, parameters)

    def upsert_import_checkpoint(self, checkpoint: Mapping[str, object]) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._upsert_checkpoint_with_cursor(cursor, checkpoint)
            connection.commit()

    def _upsert_checkpoint_with_cursor(self, cursor, checkpoint: Mapping[str, object]) -> None:
        statement = """
            INSERT INTO security_import_checkpoints (
                job_type, isin, earliest_successful_trading_date,
                latest_successful_trading_date, last_attempted_from_date,
                last_attempted_to_date, status, retry_count, last_error,
                last_successful_run_id
            ) VALUES (
                %(job_type)s, %(isin)s, %(earliest_successful_trading_date)s,
                %(latest_successful_trading_date)s, %(last_attempted_from_date)s,
                %(last_attempted_to_date)s, %(status)s, %(retry_count)s,
                %(last_error)s, %(last_successful_run_id)s
            )
            ON CONFLICT (job_type, isin) DO UPDATE SET
                earliest_successful_trading_date = CASE
                    WHEN security_import_checkpoints.earliest_successful_trading_date IS NULL
                        THEN EXCLUDED.earliest_successful_trading_date
                    WHEN EXCLUDED.earliest_successful_trading_date IS NULL
                        THEN security_import_checkpoints.earliest_successful_trading_date
                    ELSE LEAST(
                        security_import_checkpoints.earliest_successful_trading_date,
                        EXCLUDED.earliest_successful_trading_date
                    )
                END,
                latest_successful_trading_date = CASE
                    WHEN security_import_checkpoints.latest_successful_trading_date IS NULL
                        THEN EXCLUDED.latest_successful_trading_date
                    WHEN EXCLUDED.latest_successful_trading_date IS NULL
                        THEN security_import_checkpoints.latest_successful_trading_date
                    ELSE GREATEST(
                        security_import_checkpoints.latest_successful_trading_date,
                        EXCLUDED.latest_successful_trading_date
                    )
                END,
                last_attempted_from_date = EXCLUDED.last_attempted_from_date,
                last_attempted_to_date = EXCLUDED.last_attempted_to_date,
                status = EXCLUDED.status,
                retry_count = EXCLUDED.retry_count,
                last_error = EXCLUDED.last_error,
                last_successful_run_id = COALESCE(
                    EXCLUDED.last_successful_run_id,
                    security_import_checkpoints.last_successful_run_id
                ),
                updated_at = NOW()
        """
        parameters = {
            "job_type": self._enum_value(checkpoint["job_type"]),
            "isin": checkpoint["isin"],
            "earliest_successful_trading_date": checkpoint.get("earliest_successful_trading_date"),
            "latest_successful_trading_date": checkpoint.get("latest_successful_trading_date"),
            "last_attempted_from_date": checkpoint.get("last_attempted_from_date"),
            "last_attempted_to_date": checkpoint.get("last_attempted_to_date"),
            "status": self._enum_value(checkpoint["status"]),
            "retry_count": checkpoint.get("retry_count", 0),
            "last_error": checkpoint.get("last_error"),
            "last_successful_run_id": checkpoint.get("last_successful_run_id"),
        }
        cursor.execute(statement, parameters)

    def get_import_checkpoint(self, job_type: ImportJobType, isin: str) -> dict[str, object] | None:
        statement = """
            SELECT job_type, isin, earliest_successful_trading_date,
                   latest_successful_trading_date, last_attempted_from_date,
                   last_attempted_to_date, status, retry_count, last_error,
                   last_successful_run_id, updated_at
            FROM security_import_checkpoints
            WHERE job_type = %s AND isin = %s
        """
        records = self._fetch_all(statement, (job_type.value, isin))
        return records[0] if records else None

    def list_affected_security_dates(self, run_id: str) -> list[dict[str, object]]:
        statement = """
            SELECT isin, MIN(affected_date) AS earliest_affected_date,
                   MAX(affected_date) AS latest_affected_date
            FROM (
                SELECT isin, trading_date AS affected_date
                FROM nse_daily_bars_raw
                WHERE import_run_id = %s
                UNION ALL
                SELECT isin, ex_date AS affected_date
                FROM nse_corporate_actions
                WHERE import_run_id = %s
            ) AS affected_rows
            GROUP BY isin
            ORDER BY isin
        """
        return self._fetch_all(statement, (run_id, run_id))

    def _load_bars(
        self, table_name: str, isin: str, from_date: date, to_date: date
    ) -> list[dict[str, object]]:
        if table_name != "nse_daily_bars_raw":
            raise ValueError("Unsupported raw-bar table")
        statement = """
            SELECT *
            FROM nse_daily_bars_raw
            WHERE isin = %s AND trading_date >= %s AND trading_date <= %s
            ORDER BY trading_date
        """
        return self._fetch_all(statement, (isin, from_date, to_date))

    def _execute(self, statement: str, parameters: Mapping[str, object]) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
            connection.commit()

    def _fetch_all(self, statement: str, parameters: Sequence[object]) -> list[dict[str, object]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]

    def _upsert_raw_bars_with_cursor(
        self, cursor, bars: Sequence[Mapping[str, object]]
    ) -> None:
        statement = """
            INSERT INTO nse_daily_bars_raw (
                isin, trading_date, open_price, high_price, low_price, close_price,
                volume, deliverable_quantity, delivery_percentage, nse_series,
                source_name, source_checksum, source_published_at, import_run_id
            ) VALUES (
                %(isin)s, %(trading_date)s, %(open_price)s, %(high_price)s, %(low_price)s,
                %(close_price)s, %(volume)s, %(deliverable_quantity)s,
                %(delivery_percentage)s, %(nse_series)s, %(source_name)s,
                %(source_checksum)s, %(source_published_at)s, %(import_run_id)s
            )
            ON CONFLICT (isin, trading_date) DO UPDATE SET
                open_price = EXCLUDED.open_price,
                high_price = EXCLUDED.high_price,
                low_price = EXCLUDED.low_price,
                close_price = EXCLUDED.close_price,
                volume = EXCLUDED.volume,
                deliverable_quantity = EXCLUDED.deliverable_quantity,
                delivery_percentage = EXCLUDED.delivery_percentage,
                nse_series = EXCLUDED.nse_series,
                source_name = EXCLUDED.source_name,
                source_checksum = EXCLUDED.source_checksum,
                source_published_at = EXCLUDED.source_published_at,
                import_run_id = EXCLUDED.import_run_id,
                raw_revision = nse_daily_bars_raw.raw_revision + 1,
                imported_at = NOW()
            WHERE nse_daily_bars_raw.source_checksum IS DISTINCT FROM EXCLUDED.source_checksum
        """
        cursor.executemany(statement, [self._raw_bar_parameters(bar) for bar in bars])

    @staticmethod
    def _raw_bar_parameters(bar: Mapping[str, object]) -> dict[str, object]:
        return {
            "isin": bar["isin"],
            "trading_date": bar["trading_date"],
            "open_price": bar["open_price"],
            "high_price": bar["high_price"],
            "low_price": bar["low_price"],
            "close_price": bar["close_price"],
            "volume": bar["volume"],
            "deliverable_quantity": bar.get("deliverable_quantity"),
            "delivery_percentage": bar.get("delivery_percentage"),
            "nse_series": bar["nse_series"],
            "source_name": bar["source_name"],
            "source_checksum": bar["source_checksum"],
            "source_published_at": bar.get("source_published_at"),
            "import_run_id": bar.get("import_run_id"),
        }

    @staticmethod
    def _corporate_action_parameters(action: Mapping[str, object]) -> dict[str, object]:
        return {
            "source_event_key": action["source_event_key"],
            "isin": action["isin"],
            "symbol": action["symbol"],
            "action_type": action["action_type"],
            "ex_date": action["ex_date"],
            "record_date": action.get("record_date"),
            "announcement_date": action.get("announcement_date"),
            "numerator": action.get("numerator"),
            "denominator": action.get("denominator"),
            "cash_value": action.get("cash_value"),
            "currency": action.get("currency"),
            "raw_description": action.get("raw_description"),
            "raw_payload": json.dumps(serialize_value(action.get("raw_payload", {})), sort_keys=True),
            "source_checksum": action["source_checksum"],
            "import_run_id": action.get("import_run_id"),
        }

    @staticmethod
    def _enum_value(value: object) -> str:
        return str(value.value) if isinstance(value, (ImportJobType, ImportStatus)) else str(value)
