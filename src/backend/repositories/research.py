"""Persistence and point-in-time source queries for historical research."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

from pattern_engine.models import serialize_value
from repositories.migrations import MigrationRunner


_JSON_FIELDS = {"universe", "filters", "point_in_time_policy", "candidate_fingerprint", "returns_by_horizon", "mfe_by_horizon", "mae_by_horizon", "days_to_threshold", "hit_before_loss", "completeness"}


class PostgresResearchRepository:
    def __init__(self, dsn: str, *, apply_migrations: bool = True) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        if apply_migrations:
            MigrationRunner(self._connect, Path(__file__).resolve().parents[1] / "migrations").apply()

    def _connect(self):
        return psycopg.connect(self._dsn)

    def create_run(self, values):
        run_id = str(uuid4())
        columns = tuple(values)
        placeholders = [f"%({name})s" + ("::jsonb" if name in _JSON_FIELDS else "") for name in columns]
        statement = f"INSERT INTO backtest_runs (id, status, {', '.join(columns)}) VALUES (%(id)s, 'PENDING', {', '.join(placeholders)})"
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, {"id": run_id, **_json_values(values)})
            connection.commit()
        return run_id

    def update_run(self, run_id, status, **values):
        assignments = [f"{name} = %({name})s" for name in values]
        assignments.extend(["status = %(status)s", "updated_at = NOW()"])
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE backtest_runs SET {', '.join(assignments)} WHERE id = %(id)s",
                    {"id": run_id, "status": status, **values},
                )
                if cursor.rowcount != 1:
                    raise LookupError("Backtest run not found")
            connection.commit()

    def list_trading_sessions(self, from_date, to_date, adjustment_version):
        rows = self._fetch_all(
            "SELECT DISTINCT trading_date FROM adjusted_daily_bars WHERE trading_date BETWEEN %s AND %s AND adjustment_version = %s ORDER BY trading_date",
            (from_date, to_date, adjustment_version),
        )
        return [row["trading_date"] for row in rows]

    def list_historical_universe(self, index_code, as_of_date):
        return self._fetch_all(
            """
            SELECT equity.isin, equity.symbol, equity.company_name, equity.series,
                   sector.sector_code, sector.sector_name
            FROM index_constituent_memberships AS membership
            JOIN nse_equities AS equity ON equity.isin = membership.isin AND equity.listed_on <= %s
            LEFT JOIN LATERAL (
                SELECT sm.sector_code, sectors.name AS sector_name
                FROM security_sector_memberships sm
                JOIN market_sectors sectors ON sectors.code = sm.sector_code
                WHERE sm.isin = equity.isin AND sm.effective_from <= %s
                  AND (sm.effective_to IS NULL OR sm.effective_to >= %s)
                ORDER BY sm.effective_from DESC LIMIT 1
            ) sector ON TRUE
            WHERE membership.index_code = %s AND membership.effective_from <= %s
              AND (membership.effective_to IS NULL OR membership.effective_to >= %s)
            ORDER BY equity.isin
            """,
            (as_of_date, as_of_date, as_of_date, index_code, as_of_date, as_of_date),
        )

    def load_outcome_bars(self, isin, entry_date, adjustment_version, limit):
        return self._fetch_all(
            """SELECT trading_date, high_price, low_price, close_price
               FROM adjusted_daily_bars
               WHERE isin = %s AND trading_date >= %s AND adjustment_version = %s
               ORDER BY trading_date LIMIT %s""",
            (isin, entry_date, adjustment_version, limit),
        )

    def insert_entry_with_outcome(self, run_id, entry, outcome):
        entry_id = str(uuid4())
        entry_columns = tuple(entry)
        outcome_columns = tuple(outcome)
        entry_values = [f"%({name})s" + ("::jsonb" if name in _JSON_FIELDS else "") for name in entry_columns]
        outcome_values = [f"%({name})s::jsonb" for name in outcome_columns]
        parameters = {"id": entry_id, "run_id": run_id, **_json_values(entry), **{name: json.dumps(serialize_value(value), sort_keys=True) for name, value in outcome.items()}}
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO backtest_entries (id, backtest_run_id, {', '.join(entry_columns)}) VALUES (%(id)s, %(run_id)s, {', '.join(entry_values)}) ON CONFLICT (backtest_run_id, fingerprint_key) DO NOTHING",
                    parameters,
                )
                if cursor.rowcount:
                    cursor.execute(
                        f"INSERT INTO backtest_outcomes (backtest_entry_id, {', '.join(outcome_columns)}) VALUES (%(id)s, {', '.join(outcome_values)})",
                        parameters,
                    )
            connection.commit()
        return entry_id

    def get_run(self, run_id):
        rows = self._fetch_all("SELECT * FROM backtest_runs WHERE id = %s", (run_id,))
        return rows[0] if rows else None

    def list_results(self, run_id, limit, offset):
        return self._fetch_all(
            """SELECT entry.*, outcome.returns_by_horizon, outcome.mfe_by_horizon,
                      outcome.mae_by_horizon, outcome.days_to_threshold,
                      outcome.hit_before_loss, outcome.completeness
               FROM backtest_entries entry
               JOIN backtest_outcomes outcome ON outcome.backtest_entry_id = entry.id
               WHERE entry.backtest_run_id = %s
               ORDER BY entry.entry_date, entry.id LIMIT %s OFFSET %s""",
            (run_id, limit, offset),
        )

    def _fetch_all(self, statement, parameters):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]


class InMemoryResearchRepository:
    def __init__(self, *, sessions=(), memberships=None, bars=None):
        self.sessions = list(sessions)
        self.memberships = memberships or {}
        self.bars = bars or {}
        self.runs = {}
        self.entries = []

    def create_run(self, values):
        run_id = str(uuid4())
        self.runs[run_id] = {"id": run_id, "status": "PENDING", "sessions_processed": 0, "securities_evaluated": 0, "entries_recorded": 0, "created_at": datetime.now(timezone.utc), **dict(values)}
        return run_id

    def update_run(self, run_id, status, **values):
        if run_id not in self.runs: raise LookupError("Backtest run not found")
        self.runs[run_id].update(status=status, **values)

    def list_trading_sessions(self, from_date, to_date, adjustment_version):
        return [value for value in self.sessions if from_date <= value <= to_date]

    def list_historical_universe(self, index_code, as_of_date):
        return [dict(row) for row in self.memberships.get((index_code, as_of_date), ())]

    def load_outcome_bars(self, isin, entry_date, adjustment_version, limit):
        return [dict(row) for row in self.bars.get(isin, ()) if row["trading_date"] >= entry_date][:limit]

    def insert_entry_with_outcome(self, run_id, entry, outcome):
        entry_id = str(uuid4())
        if any(row["backtest_run_id"] == run_id and row["fingerprint_key"] == entry["fingerprint_key"] for row in self.entries): return entry_id
        self.entries.append({"id": entry_id, "backtest_run_id": run_id, **dict(entry), **dict(outcome)})
        return entry_id

    def get_run(self, run_id):
        row = self.runs.get(run_id)
        return dict(row) if row else None

    def list_results(self, run_id, limit, offset):
        rows = [dict(row) for row in self.entries if row["backtest_run_id"] == run_id]
        return rows[offset:offset + limit]


def _json_values(values):
    return {name: json.dumps(serialize_value(value), sort_keys=True) if name in _JSON_FIELDS else value for name, value in values.items()}
