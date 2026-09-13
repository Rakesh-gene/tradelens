"""PostgreSQL persistence for admin-selected pipeline runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from uuid import uuid4

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

from pattern_engine.models import serialize_value
from repositories.migrations import MigrationRunner


class PostgresAdminPipelineRepository:
    def __init__(self, dsn: str, *, apply_migrations: bool = True) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        if apply_migrations:
            MigrationRunner(self._connect, Path(__file__).resolve().parents[1] / "migrations").apply()

    def _connect(self):
        return psycopg.connect(self._dsn)

    def list_equities(self, search, page, page_size):
        pattern = f"%{search}%" if search else None
        total_row = self._fetch_one(
            """SELECT COUNT(*) AS total FROM nse_equities
               WHERE series = 'EQ' AND (%s::text IS NULL OR symbol ILIKE %s OR company_name ILIKE %s OR isin ILIKE %s)""",
            (pattern, pattern, pattern, pattern),
        ) or {"total": 0}
        rows = self._fetch_all(
            """SELECT equity.isin, equity.symbol, equity.company_name, equity.series, equity.listed_on,
                      latest.latest_raw_date, recent.status AS last_pipeline_status,
                      recent.finished_at AS last_pipeline_at,
                      classification.sector_code, classification.sector_name,
                      classification.basic_industry_name,
                      COALESCE(classification.status, 'MISSING') AS classification_status
               FROM nse_equities equity
               LEFT JOIN LATERAL (
                   SELECT membership.sector_code, sector.name AS sector_name,
                          basic.name AS basic_industry_name, refresh.status
                   FROM security_sector_memberships membership
                   JOIN market_sectors sector ON sector.code = membership.sector_code
                   LEFT JOIN security_industry_memberships sim ON sim.isin = equity.isin AND sim.effective_to IS NULL
                   LEFT JOIN market_basic_industries basic ON basic.code = sim.basic_industry_code
                   LEFT JOIN equity_classification_refresh_state refresh ON refresh.isin = equity.isin
                   WHERE membership.isin = equity.isin AND membership.effective_to IS NULL
                   ORDER BY membership.effective_from DESC LIMIT 1
               ) classification ON TRUE
               LEFT JOIN LATERAL (
                   SELECT MAX(trading_date) AS latest_raw_date FROM nse_daily_bars_raw
                   WHERE isin = equity.isin
               ) latest ON TRUE
               LEFT JOIN LATERAL (
                   SELECT item.status, item.finished_at FROM admin_pipeline_run_items item
                   WHERE item.isin = equity.isin ORDER BY item.updated_at DESC LIMIT 1
               ) recent ON TRUE
               WHERE equity.series = 'EQ'
                 AND (%s::text IS NULL OR equity.symbol ILIKE %s OR equity.company_name ILIKE %s OR equity.isin ILIKE %s)
               ORDER BY equity.symbol, equity.isin LIMIT %s OFFSET %s""",
            (pattern, pattern, pattern, pattern, page_size, (page - 1) * page_size),
        )
        return rows, int(total_row["total"])

    def get_equities(self, isins: Sequence[str]):
        if not isins:
            return []
        placeholders = ", ".join(["%s"] * len(isins))
        return self._fetch_all(
            f"""SELECT isin, symbol, company_name, series, listed_on
                FROM nse_equities WHERE series = 'EQ' AND isin IN ({placeholders})
                ORDER BY symbol, isin""",
            tuple(isins),
        )

    def list_all_equities(self):
        return self._fetch_all(
            """SELECT isin, symbol, company_name, series, listed_on
               FROM nse_equities WHERE series = 'EQ' ORDER BY symbol, isin""",
            (),
        )

    def create_pipeline_run(self, values, securities):
        run_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    '''INSERT INTO admin_pipeline_runs (
                       id, requested_by, requested_from_date, requested_to_date,
                       versions, force_refresh, run_scope, batch_size, status,
                       securities_total, trigger_source, scheduled_for, run_kind,
                       requested_timeframes, pattern_groups
                       ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s::jsonb, %s::jsonb)''',
                    (run_id, values['requested_by'], values['requested_from_date'],
                     values['requested_to_date'], json.dumps(serialize_value(values['versions']), sort_keys=True),
                     values['force_refresh'], values.get('run_scope', 'SELECTION'),
                     values.get('batch_size', 25), values['status'], len(securities),
                     values.get('trigger_source', 'MANUAL'), values.get('scheduled_for'),
                     values.get('run_kind', 'FULL_PIPELINE'),
                     json.dumps(list(values.get('requested_timeframes') or ('1D',))),
                     json.dumps(list(values.get('pattern_groups') or ()))),
                )
                cursor.executemany(
                    """INSERT INTO admin_pipeline_run_items
                           (run_id, isin, symbol, status, current_stage)
                       VALUES (%s, %s, %s, 'PENDING', 'QUEUED')""",
                    [(run_id, row["isin"], row["symbol"]) for row in securities],
                )
            connection.commit()
        return run_id

    def scheduled_pipeline_run_exists(self, scheduled_for):
        return self.get_scheduled_pipeline_run(scheduled_for) is not None

    def get_scheduled_pipeline_run(self, scheduled_for):
        return self._fetch_one(
            """SELECT id, status, resume_count FROM admin_pipeline_runs
               WHERE trigger_source = 'SCHEDULED' AND scheduled_for = %s
               ORDER BY created_at DESC LIMIT 1""",
            (scheduled_for,),
        )

    def active_pipeline_run_exists(self):
        return self._fetch_one(
            """SELECT id FROM admin_pipeline_runs
               WHERE status IN ('PENDING', 'RUNNING', 'PAUSED') LIMIT 1""",
            (),
        ) is not None

    def fail_interrupted_pipeline_runs(self):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE admin_pipeline_run_items item
                       SET status = 'FAILED', current_stage = 'INTERRUPTED',
                           error_message = COALESCE(item.error_message, 'Backend stopped before this equity completed'),
                           finished_at = COALESCE(item.finished_at, NOW()), updated_at = NOW()
                       FROM admin_pipeline_runs run
                       WHERE item.run_id = run.id
                         AND run.status IN ('PENDING', 'RUNNING')
                         AND item.status IN ('PENDING', 'RUNNING')"""
                )
                cursor.execute(
                    """UPDATE admin_pipeline_runs
                       SET status = 'FAILED', finished_at = NOW(),
                           error_summary = COALESCE(error_summary, 'Backend stopped before the pipeline completed')
                       WHERE status IN ('PENDING', 'RUNNING')
                       RETURNING id"""
                )
                interrupted = len(cursor.fetchall())
            connection.commit()
        return interrupted

    def update_pipeline_run(self, run_id, status, **values):
        self._execute(
            """UPDATE admin_pipeline_runs SET status = %(status)s,
                   started_at = CASE WHEN %(started)s THEN COALESCE(started_at, NOW()) ELSE started_at END,
                   finished_at = CASE WHEN %(finished)s THEN NOW() ELSE finished_at END,
                   securities_completed = COALESCE(%(completed)s, securities_completed),
                   securities_failed = COALESCE(%(failed)s, securities_failed),
                   error_summary = COALESCE(%(error)s, error_summary)
               WHERE id = %(run_id)s""",
            {"run_id": run_id, "status": status, "started": bool(values.get("started")),
             "finished": bool(values.get("finished")), "completed": values.get("securities_completed"),
             "failed": values.get("securities_failed"), "error": values.get("error_summary")},
        )

    def pipeline_run_status(self, run_id):
        row = self._fetch_one(
            "SELECT status FROM admin_pipeline_runs WHERE id = %s", (run_id,)
        )
        return str(row["status"]) if row else None

    def pause_pipeline_run(self, run_id):
        return self._transition_pipeline_run(
            run_id, ("PENDING", "RUNNING"), "PAUSED", "paused_at = NOW()"
        )

    def terminate_pipeline_run(self, run_id):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE admin_pipeline_runs
                       SET status = 'TERMINATED', terminated_at = NOW(), finished_at = NOW()
                       WHERE id = %s AND status IN ('PENDING', 'RUNNING', 'PAUSED')
                       RETURNING id""",
                    (run_id,),
                )
                changed = cursor.fetchone() is not None
                if changed:
                    cursor.execute(
                        """UPDATE admin_pipeline_run_items
                           SET status = 'CANCELLED', current_stage = 'CANCELLED',
                               finished_at = NOW(), updated_at = NOW()
                           WHERE run_id = %s AND status = 'PENDING'""",
                        (run_id,),
                    )
            connection.commit()
        return changed

    def prepare_pipeline_run_resume(self, run_id):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT status FROM admin_pipeline_runs WHERE id = %s FOR UPDATE""",
                    (run_id,),
                )
                row = cursor.fetchone()
                if row is None or row[0] not in {"FAILED", "PARTIAL", "PAUSED"}:
                    return []
                cursor.execute(
                    """UPDATE admin_pipeline_run_items
                       SET status = 'PENDING', current_stage = 'QUEUED',
                           finished_at = NULL, error_message = NULL, updated_at = NOW()
                       WHERE run_id = %s AND status <> 'COMPLETED'""",
                    (run_id,),
                )
                cursor.execute(
                    """UPDATE admin_pipeline_runs
                       SET status = 'PENDING', securities_failed = 0,
                           error_summary = NULL, finished_at = NULL, paused_at = NULL,
                           last_resumed_at = NOW(), resume_count = resume_count + 1
                       WHERE id = %s""",
                    (run_id,),
                )
                cursor.execute(
                    """SELECT isin, symbol FROM admin_pipeline_run_items
                       WHERE run_id = %s AND status = 'PENDING'
                       ORDER BY symbol, isin""",
                    (run_id,),
                )
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
            connection.commit()
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]

    def _transition_pipeline_run(self, run_id, from_statuses, to_status, assignments):
        placeholders = ", ".join(["%s"] * len(from_statuses))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""UPDATE admin_pipeline_runs
                        SET status = %s, {assignments}
                        WHERE id = %s AND status IN ({placeholders})
                        RETURNING id""",
                    (to_status, run_id, *from_statuses),
                )
                changed = cursor.fetchone() is not None
            connection.commit()
        return changed

    def update_pipeline_item(self, run_id, isin, status, stage, **values):
        self._execute(
            """UPDATE admin_pipeline_run_items SET status = %(status)s, current_stage = %(stage)s,
                   started_at = CASE WHEN %(started)s THEN COALESCE(started_at, NOW()) ELSE started_at END,
                   finished_at = CASE WHEN %(finished)s THEN NOW() ELSE finished_at END,
                   history_run_id = COALESCE(%(history_run_id)s, history_run_id),
                   pattern_run_id = COALESCE(%(pattern_run_id)s, pattern_run_id),
                   rows_downloaded = COALESCE(%(rows_downloaded)s, rows_downloaded),
                   candidates_detected = COALESCE(%(candidates)s, candidates_detected),
                   error_message = COALESCE(%(error)s, error_message),
                   attempt_count = attempt_count + CASE WHEN %(started)s THEN 1 ELSE 0 END,
                   updated_at = NOW()
               WHERE run_id = %(run_id)s AND isin = %(isin)s""",
            {"run_id": run_id, "isin": isin, "status": status, "stage": stage,
             "started": bool(values.get("started")), "finished": bool(values.get("finished")),
             "history_run_id": values.get("history_run_id"), "pattern_run_id": values.get("pattern_run_id"),
             "rows_downloaded": values.get("rows_downloaded"),
             "candidates": values.get("candidates_detected"), "error": values.get("error_message")},
        )

    def get_pipeline_run(self, run_id, item_page=1, item_page_size=25):
        run = self._fetch_one(
            """SELECT pipeline.*,
                      (SELECT COUNT(1) FROM admin_pipeline_run_items item
                       WHERE item.run_id = pipeline.id
                         AND item.current_stage = 'SECTOR_CONTEXT') AS securities_prepared
               FROM admin_pipeline_runs pipeline WHERE pipeline.id = %s""",
            (run_id,),
        )
        if run is None:
            return None
        run["items"] = self._fetch_all(
            """SELECT * FROM admin_pipeline_run_items WHERE run_id = %s
               ORDER BY symbol, isin LIMIT %s OFFSET %s""",
            (run_id, item_page_size, (item_page - 1) * item_page_size),
        )
        return run

    def list_pipeline_runs(self, page, page_size):
        total = self._fetch_one("SELECT COUNT(*) AS total FROM admin_pipeline_runs", ()) or {"total": 0}
        rows = self._fetch_all(
            "SELECT * FROM admin_pipeline_runs ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (page_size, (page - 1) * page_size),
        )
        return rows, int(total["total"])

    def _execute(self, statement, parameters):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
            connection.commit()

    def _fetch_one(self, statement, parameters):
        rows = self._fetch_all(statement, parameters)
        return rows[0] if rows else None

    def _fetch_all(self, statement, parameters):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]
