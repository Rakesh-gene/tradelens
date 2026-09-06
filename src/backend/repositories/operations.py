"""PostgreSQL queries for operational events, health, and coverage checks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

from pattern_engine.models import serialize_value
from repositories.migrations import MigrationRunner


class PostgresOperationsRepository:
    def __init__(self, dsn, *, apply_migrations=True):
        if psycopg is None: raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        if apply_migrations: MigrationRunner(self._connect, Path(__file__).resolve().parents[1] / "migrations").apply()

    def _connect(self): return psycopg.connect(self._dsn)

    def record_operational_event(self, event):
        event_id = str(uuid4())
        known = {name: event.get(name) for name in ("level", "event_type", "run_id", "job_type", "isin", "symbol", "requested_from_date", "requested_to_date", "attempt", "duration_ms", "row_count", "source_status", "error_class")}
        details = {key: value for key, value in event.items() if key not in {*known, "occurred_at"}}
        self._execute(
            """INSERT INTO operational_events (id, level, event_type, run_id, job_type, isin, symbol,
                   requested_from_date, requested_to_date, attempt, duration_ms, row_count,
                   source_status, error_class, details, occurred_at)
               VALUES (%(id)s, %(level)s, %(event_type)s, %(run_id)s, %(job_type)s, %(isin)s, %(symbol)s,
                   %(requested_from_date)s, %(requested_to_date)s, %(attempt)s, %(duration_ms)s,
                   %(row_count)s, %(source_status)s, %(error_class)s, %(details)s::jsonb, %(occurred_at)s)""",
            {"id": event_id, **known, "details": json.dumps(serialize_value(details), sort_keys=True), "occurred_at": event.get("occurred_at")},
        )
        return event_id

    def operational_health(self):
        runs = self._fetch_all(
            """SELECT DISTINCT ON (job_type) job_type, id AS run_id, status, started_at, finished_at,
                      duration_ms, securities_total, securities_completed, securities_failed,
                      rows_downloaded, rows_inserted, rows_updated, rows_rejected, source_metrics, stage_metrics
               FROM market_import_runs WHERE status IN ('COMPLETED','PARTIAL','FAILED')
               ORDER BY job_type, started_at DESC""", (),
        )
        successful_runs = self._fetch_all(
            """SELECT DISTINCT ON (job_type) job_type, id AS run_id, status, started_at, finished_at,
                      duration_ms, securities_total, securities_completed, securities_failed,
                      rows_downloaded, rows_inserted, rows_updated, rows_rejected, source_metrics, stage_metrics
               FROM market_import_runs WHERE status = 'COMPLETED'
               ORDER BY job_type, started_at DESC""", (),
        )
        checkpoints = self._fetch_all(
            """SELECT job_type, MAX(updated_at) AS last_checkpoint_at,
                      COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed_securities,
                      COUNT(*) FILTER (WHERE status = 'FAILED') AS failed_securities,
                      MAX(latest_successful_trading_date) AS latest_data_date
               FROM security_import_checkpoints
               GROUP BY job_type ORDER BY job_type""", (),
        )
        freshness = self._fetch_one(
            """SELECT (SELECT MAX(trading_date) FROM nse_daily_bars_raw) AS raw_data_date,
                      (SELECT MAX(trading_date) FROM adjusted_daily_bars) AS adjusted_data_date,
                      (SELECT MAX(trading_date) FROM technical_features) AS feature_date,
                      (SELECT MAX(last_updated_date) FROM pattern_instances) AS pattern_date,
                      (SELECT COUNT(*) FROM pattern_instances WHERE terminal_date IS NULL) AS active_patterns,
                      (SELECT COUNT(*) FROM pattern_events) AS pattern_events,
                      (SELECT COUNT(*) FROM pattern_scan_failures) AS scan_failures,
                      (SELECT COUNT(*) FROM data_quality_anomalies WHERE resolved_at IS NULL) AS open_anomalies""", (),
        ) or {}
        newest = freshness.get("raw_data_date")
        freshness["adjustment_lag_days"] = _date_lag(newest, freshness.get("adjusted_data_date"))
        freshness["feature_lag_days"] = _date_lag(newest, freshness.get("feature_date"))
        freshness["pattern_lag_days"] = _date_lag(newest, freshness.get("pattern_date"))
        return {"latestRuns": runs, "lastSuccessfulRuns": successful_runs, "lastCheckpoints": checkpoints, "pipeline": freshness}

    def validate_coverage(self, from_date, to_date, limit):
        return self._fetch_all(
            """WITH bounds AS (
                   SELECT COALESCE(%s, MIN(trading_date)) AS from_date,
                          COALESCE(%s, MAX(trading_date)) AS to_date FROM nse_daily_bars_raw
               ), sessions AS (
                   SELECT DISTINCT trading_date FROM nse_daily_bars_raw, bounds
                   WHERE trading_date BETWEEN bounds.from_date AND bounds.to_date
               ), coverage AS (
                   SELECT equity.isin, equity.symbol, bounds.from_date, bounds.to_date,
                          COUNT(bar.trading_date) AS bar_count,
                          (SELECT COUNT(*) FROM sessions s WHERE s.trading_date >= GREATEST(bounds.from_date, equity.listed_on)) - COUNT(bar.trading_date) AS missing_sessions,
                          MIN(bar.trading_date) AS first_bar_date, MAX(bar.trading_date) AS last_bar_date
                   FROM nse_equities equity CROSS JOIN bounds
                   LEFT JOIN nse_daily_bars_raw bar ON bar.isin = equity.isin
                     AND bar.trading_date BETWEEN GREATEST(bounds.from_date, equity.listed_on) AND bounds.to_date
                   WHERE equity.series = 'EQ'
                   GROUP BY equity.isin, equity.symbol, equity.listed_on, bounds.from_date, bounds.to_date
               ) SELECT * FROM coverage ORDER BY missing_sessions DESC, isin LIMIT %s""",
            (from_date, to_date, limit),
        )

    def upsert_anomalies(self, anomalies):
        if not anomalies: return 0
        statement = """INSERT INTO data_quality_anomalies (id, anomaly_type, severity, isin, trading_date, details)
                       VALUES (%(id)s, %(anomaly_type)s, %(severity)s, %(isin)s, %(trading_date)s, %(details)s::jsonb)
                       ON CONFLICT (anomaly_type, isin, trading_date) DO UPDATE SET
                         severity=EXCLUDED.severity, details=EXCLUDED.details, detected_at=NOW(), resolved_at=NULL"""
        parameters = [{"id": str(uuid4()), **row, "details": json.dumps(serialize_value(row.get("details") or {}), sort_keys=True)} for row in anomalies]
        with self._connect() as connection:
            with connection.cursor() as cursor: cursor.executemany(statement, parameters)
            connection.commit()
        return len(parameters)

    def pattern_lineage(self, pattern_id):
        pattern = self._fetch_one(
            """SELECT id, isin, pattern_type, variant, start_date, detected_date, last_updated_date,
                      configuration_version, engine_version, feature_version, adjustment_version,
                      measurements, supporting_patterns
               FROM pattern_instances WHERE id = %s""", (pattern_id,),
        )
        if pattern is None: return None
        bars = self._fetch_all(
            """SELECT trading_date, adjustment_source, source_revision, action_set_checksum,
                      price_adjustment_factor, volume_adjustment_factor
               FROM adjusted_daily_bars WHERE isin = %s AND adjustment_version = %s
                 AND trading_date BETWEEN %s AND %s ORDER BY trading_date""",
            (pattern["isin"], pattern["adjustment_version"], pattern["start_date"], pattern["last_updated_date"]),
        )
        actions = self._fetch_all(
            """SELECT source_event_key, action_type, ex_date, source_checksum
               FROM nse_corporate_actions WHERE isin = %s AND ex_date <= %s ORDER BY ex_date, source_event_key""",
            (pattern["isin"], pattern["last_updated_date"]),
        )
        features = self._fetch_all(
            """SELECT trading_date, feature_version, data_version, input_checksum
               FROM technical_features WHERE isin = %s AND feature_version = %s
                 AND trading_date BETWEEN %s AND %s ORDER BY trading_date""",
            (pattern["isin"], pattern["feature_version"], pattern["start_date"], pattern["last_updated_date"]),
        )
        return {"pattern": pattern, "adjustedBars": bars, "corporateActions": actions, "features": features}

    def _execute(self, statement, parameters):
        with self._connect() as connection:
            with connection.cursor() as cursor: cursor.execute(statement, parameters)
            connection.commit()

    def _fetch_one(self, statement, parameters):
        rows = self._fetch_all(statement, parameters)
        return rows[0] if rows else None

    def _fetch_all(self, statement, parameters):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters); rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]


def _date_lag(source, downstream):
    return None if source is None or downstream is None else max(0, (source - downstream).days)
