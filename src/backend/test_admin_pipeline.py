from datetime import date
from pathlib import Path
from threading import Barrier, Lock
import unittest

from data_pipeline.history_backfill import BackfillRunResult, SecurityBackfillResult
from operations.admin_pipeline import AdminPipelineService
from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import ImportStatus
from repositories.admin_pipeline import PostgresAdminPipelineRepository


class PipelineRepository:
    def __init__(self):
        self.equities = [
            {"isin": "INE002A01018", "symbol": "RELIANCE", "company_name": "Reliance Industries Limited", "series": "EQ", "listed_on": date(1995, 1, 1)},
            {"isin": "INE467B01029", "symbol": "TCS", "company_name": "Tata Consultancy Services", "series": "EQ", "listed_on": date(2004, 8, 25)},
        ]
        self.runs = {}

    def list_equities(self, search, page, page_size):
        rows = [row for row in self.equities if not search or search.lower() in row["symbol"].lower()]
        return rows[(page - 1) * page_size:page * page_size], len(rows)

    def get_equities(self, isins): return [row for row in self.equities if row["isin"] in isins]
    def list_all_equities(self): return list(self.equities)
    def scheduled_pipeline_run_exists(self, scheduled_for):
        return self.get_scheduled_pipeline_run(scheduled_for) is not None
    def get_scheduled_pipeline_run(self, scheduled_for):
        return next((
            run for run in self.runs.values()
            if run.get("trigger_source") == "SCHEDULED"
            and run.get("scheduled_for") == scheduled_for
        ), None)
    def active_pipeline_run_exists(self):
        return any(run.get("status") in {"PENDING", "RUNNING", "PAUSED"} for run in self.runs.values())
    def fail_interrupted_pipeline_runs(self):
        interrupted = 0
        for run in self.runs.values():
            if run.get("status") in {"PENDING", "RUNNING"}:
                run["status"] = "FAILED"
                interrupted += 1
        return interrupted
    def create_pipeline_run(self, values, securities):
        run_id = "admin-run-1"
        self.runs[run_id] = {"id": run_id, **dict(values), "securities_total": len(securities), "securities_completed": 0, "securities_failed": 0, "items": [{"isin": row["isin"], "symbol": row["symbol"], "status": "PENDING", "current_stage": "QUEUED"} for row in securities]}
        return run_id
    def update_pipeline_run(self, run_id, status, **values):
        self.runs[run_id].update(status=status, **{key: value for key, value in values.items() if key not in {"started", "finished"}})
    def pipeline_run_status(self, run_id): return self.runs.get(run_id, {}).get("status")
    def pause_pipeline_run(self, run_id):
        if self.pipeline_run_status(run_id) not in {"PENDING", "RUNNING"}: return False
        self.runs[run_id]["status"] = "PAUSED"; return True
    def terminate_pipeline_run(self, run_id):
        if self.pipeline_run_status(run_id) not in {"PENDING", "RUNNING", "PAUSED"}: return False
        self.runs[run_id]["status"] = "TERMINATED"
        for item in self.runs[run_id]["items"]:
            if item["status"] == "PENDING": item.update(status="CANCELLED", current_stage="CANCELLED")
        return True
    def prepare_pipeline_run_resume(self, run_id):
        if self.pipeline_run_status(run_id) not in {"FAILED", "PARTIAL", "PAUSED"}: return []
        run = self.runs[run_id]
        pending = []
        for item in run["items"]:
            if item["status"] != "COMPLETED":
                item.update(status="PENDING", current_stage="QUEUED", error_message=None)
                pending.append({"isin": item["isin"], "symbol": item["symbol"]})
        run.update(status="PENDING", securities_failed=0, error_summary=None)
        run["resume_count"] = run.get("resume_count", 0) + 1
        return pending
    def update_pipeline_item(self, run_id, isin, status, stage, **values):
        item = next(row for row in self.runs[run_id]["items"] if row["isin"] == isin)
        item.update(status=status, current_stage=stage, **{key: value for key, value in values.items() if key not in {"started", "finished"}})
    def get_pipeline_run(self, run_id, item_page=1, item_page_size=25):
        run = self.runs.get(run_id)
        if run is None: return None
        start = (item_page - 1) * item_page_size
        return {**run, "items": run["items"][start:start + item_page_size]}
    def list_pipeline_runs(self, page, page_size): return list(self.runs.values()), len(self.runs)


class HistoryService:
    def __init__(self, failed=()): self.failed = set(failed); self.requests = []
    def run(self, request):
        self.requests.append(request)
        error = "NSE unavailable" if request.isin in self.failed else None
        item = SecurityBackfillResult(request.isin, request.isin, request.from_date, request.to_date, [], rows_downloaded=12, error=error)
        return BackfillRunResult("history-run", ImportStatus.PARTIAL if error else ImportStatus.COMPLETED, (item,))


class ConcurrentHistoryService(HistoryService):
    def __init__(self):
        super().__init__()
        self._barrier = Barrier(2)
        self._lock = Lock()
        self._active = 0
        self.max_active = 0

    def run(self, request):
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            self._barrier.wait(timeout=2)
            return super().run(request)
        finally:
            with self._lock:
                self._active -= 1


class RecoveryService:
    def __init__(self): self.calls = []
    def rebuild_security(self, isin, from_date, to_date, versions, dry_run=False):
        self.calls.append((isin, from_date, to_date, versions))
        return {"runId": f"pattern-{isin}", "status": "COMPLETED", "metrics": {"candidatesDetected": 3}}


class AdminPipelineServiceTestCase(unittest.TestCase):
    def _service(self, failed=()):
        self.repository = PipelineRepository()
        self.history = HistoryService(failed)
        self.recovery = RecoveryService()
        return AdminPipelineService(
            self.repository, self.history, self.recovery,
            load_pattern_engine_configuration(), executor=lambda action: action(),
            today=lambda: date(2026, 9, 5),
            max_workers=1,
        )

    def test_lists_paginated_equities_and_runs_every_stage_for_selected_rows(self):
        service = self._service()
        page = service.list_equities({"page": ["1"], "pageSize": ["10"], "search": ["REL"]})
        result = service.start({"isins": ["INE002A01018"], "fromDate": "2024-01-01", "toDate": "2024-01-31"}, "admin-1")

        self.assertEqual(["RELIANCE"], [row["symbol"] for row in page["items"]])
        self.assertEqual("COMPLETED", result["run"]["status"])
        self.assertEqual("COMPLETED", result["run"]["items"][0]["status"])
        self.assertEqual(12, result["run"]["items"][0]["rowsDownloaded"])
        self.assertEqual(3, result["run"]["items"][0]["candidatesDetected"])
        self.assertEqual(["INE002A01018"], [call[0] for call in self.recovery.calls])
        self.assertEqual(
            (date(2024, 1, 1), date(2024, 1, 31)),
            self.recovery.calls[0][1:3],
        )

    def test_one_source_failure_is_isolated_and_parent_is_partial(self):
        service = self._service({"INE467B01029"})
        result = service.start({"isins": ["INE002A01018", "INE467B01029"]}, "admin-1")

        self.assertEqual("PARTIAL", result["run"]["status"])
        self.assertEqual(1, result["run"]["securitiesCompleted"])
        self.assertEqual(1, result["run"]["securitiesFailed"])
        self.assertEqual(["COMPLETED", "FAILED"], [item["status"] for item in result["run"]["items"]])

    def test_resume_retries_only_unfinished_equities_and_preserves_completed_work(self):
        service = self._service({"INE467B01029"})
        first = service.start({"allEquities": True}, "admin-1")
        self.assertEqual("PARTIAL", first["run"]["status"])

        self.history.failed.clear()
        resumed = service.resume(first["run"]["runId"])

        self.assertEqual("COMPLETED", resumed["run"]["status"])
        self.assertEqual(2, resumed["run"]["securitiesCompleted"])
        self.assertEqual(0, resumed["run"]["securitiesFailed"])
        self.assertEqual(
            ["INE002A01018", "INE467B01029", "INE467B01029"],
            [request.isin for request in self.history.requests],
        )

    def test_pause_and_terminate_prevent_the_next_equity_from_starting(self):
        actions = []
        repository = PipelineRepository()
        history = HistoryService()
        service = AdminPipelineService(
            repository, history, RecoveryService(),
            load_pattern_engine_configuration(), executor=actions.append,
            today=lambda: date(2026, 9, 5),
            max_workers=1,
        )

        paused = service.start({"allEquities": True}, "admin-1")
        service.pause(paused["run"]["runId"])
        actions.pop(0)()
        self.assertEqual([], history.requests)
        self.assertEqual("PAUSED", repository.runs[paused["run"]["runId"]]["status"])

        service.resume(paused["run"]["runId"])
        service.terminate(paused["run"]["runId"])
        actions.pop(0)()
        self.assertEqual([], history.requests)
        self.assertEqual("TERMINATED", repository.runs[paused["run"]["runId"]]["status"])
        self.assertTrue(all(
            item["status"] == "CANCELLED"
            for item in repository.runs[paused["run"]["runId"]]["items"]
        ))

    def test_run_all_snapshots_every_equity_and_processes_bounded_batches(self):
        service = self._service()

        result = service.start({"allEquities": True, "batchSize": 1}, "admin-1")

        self.assertEqual("ALL", result["run"]["runScope"])
        self.assertEqual(1, result["run"]["batchSize"])
        self.assertEqual(2, result["run"]["securitiesTotal"])
        self.assertEqual(2, result["run"]["securitiesCompleted"])
        self.assertEqual(
            ["INE002A01018", "INE467B01029"],
            [request.isin for request in self.history.requests],
        )
        self.assertEqual(
            ["INE002A01018", "INE467B01029"],
            [call[0] for call in self.recovery.calls],
        )

    def test_run_all_processes_independent_equities_concurrently(self):
        repository = PipelineRepository()
        history = ConcurrentHistoryService()
        service = AdminPipelineService(
            repository, history, RecoveryService(),
            load_pattern_engine_configuration(), executor=lambda action: action(),
            today=lambda: date(2026, 9, 5), max_workers=2,
        )

        result = service.start({"allEquities": True}, "admin-1")

        self.assertEqual("COMPLETED", result["run"]["status"])
        self.assertEqual(2, history.max_active)

    def test_run_all_rejects_selection_and_invalid_batch_size(self):
        service = self._service()
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            service.start({"allEquities": True, "isins": ["INE002A01018"]}, "admin-1")
        with self.assertRaisesRegex(ValueError, "batchSize"):
            service.start({"allEquities": True, "batchSize": 101}, "admin-1")

    def test_scheduled_run_is_incremental_unattended_and_idempotent(self):
        service = self._service()

        first = service.ensure_scheduled_run(date(2026, 9, 7), batch_size=1)
        second = service.ensure_scheduled_run(date(2026, 9, 7), batch_size=1)

        self.assertEqual("STARTED", first)
        self.assertEqual("ALREADY_SCHEDULED", second)
        run = self.repository.runs["admin-run-1"]
        self.assertIsNone(run["requested_by"])
        self.assertEqual("SCHEDULED", run["trigger_source"])
        self.assertEqual(date(2026, 9, 7), run["scheduled_for"])
        self.assertFalse(run["force_refresh"])
        self.assertTrue(all(request.initiated_by == "scheduler" for request in self.history.requests))

    def test_interrupted_scheduled_run_is_automatically_resumed_once(self):
        service = self._service({"INE467B01029"})
        self.assertEqual("STARTED", service.ensure_scheduled_run(date(2026, 9, 7)))
        self.assertEqual("PARTIAL", self.repository.runs["admin-run-1"]["status"])

        self.history.failed.clear()
        self.assertEqual("RESUMED", service.ensure_scheduled_run(date(2026, 9, 7)))
        self.assertEqual("COMPLETED", self.repository.runs["admin-run-1"]["status"])

    def test_scheduled_run_waits_while_another_run_is_active(self):
        actions = []
        self.repository = PipelineRepository()
        service = AdminPipelineService(
            self.repository, HistoryService(), RecoveryService(),
            load_pattern_engine_configuration(), executor=actions.append,
            today=lambda: date(2026, 9, 7), max_workers=1,
        )
        service.start({"allEquities": True}, "admin-1")

        self.assertEqual(
            "ACTIVE_RUN", service.ensure_scheduled_run(date(2026, 9, 7))
        )

    def test_interrupted_runs_are_recovered_as_failed_on_startup(self):
        actions = []
        service = AdminPipelineService(
            self.repository if hasattr(self, "repository") else PipelineRepository(),
            HistoryService(), RecoveryService(), load_pattern_engine_configuration(),
            executor=actions.append, max_workers=1,
        )
        service.start({"allEquities": True}, "admin-1")

        self.assertEqual(1, service.recover_interrupted_runs())
        self.assertEqual("FAILED", service.list_runs({})["items"][0]["status"])

    def test_unknown_and_oversized_selection_are_rejected_before_scheduling(self):
        service = self._service()
        with self.assertRaisesRegex(ValueError, "Unknown"):
            service.start({"isins": ["UNKNOWN"]}, "admin-1")
        with self.assertRaisesRegex(ValueError, "at most"):
            service.start({"isins": [f"ISIN{index}" for index in range(101)]}, "admin-1")


class AdminPipelineMigrationTestCase(unittest.TestCase):
    def test_run_and_per_security_status_tables_are_idempotent_and_auditable(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "016_create_admin_pipeline_runs.sql").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS admin_pipeline_runs", sql)
        self.assertIn("requested_by UUID NOT NULL REFERENCES users", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS admin_pipeline_run_items", sql)
        self.assertIn("PRIMARY KEY (run_id, isin)", sql)
        self.assertIn("history_run_id UUID REFERENCES market_import_runs", sql)
        self.assertIn("pattern_run_id UUID REFERENCES market_import_runs", sql)

    def test_run_scope_and_batch_size_migration_is_idempotent(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "018_extend_admin_pipeline_run_scope.sql").read_text(encoding="utf-8")

        self.assertIn("ADD COLUMN IF NOT EXISTS run_scope", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS batch_size", sql)
        self.assertIn("CHECK (run_scope IN ('SELECTION', 'ALL'))", sql)
        self.assertIn("CHECK (batch_size BETWEEN 1 AND 100)", sql)

    def test_run_control_migration_adds_auditable_resume_metadata(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "019_add_admin_pipeline_controls.sql").read_text(encoding="utf-8")

        self.assertIn("ADD COLUMN IF NOT EXISTS paused_at", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS terminated_at", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS resume_count", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS attempt_count", sql)

    def test_scheduler_migration_supports_one_unattended_run_per_day(self):
        sql = (Path(__file__).resolve().parent / "migrations" / "021_add_pipeline_scheduling.sql").read_text(encoding="utf-8")

        self.assertIn("ALTER COLUMN requested_by DROP NOT NULL", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS trigger_source", sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS scheduled_for", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS", sql)


class AdminPipelineRepositoryTestCase(unittest.TestCase):
    def test_blank_equity_search_is_explicitly_typed_for_postgres(self):
        class RecordingRepository(PostgresAdminPipelineRepository):
            def __init__(self): self.statements = []
            def _fetch_one(self, statement, parameters):
                self.statements.append((statement, parameters)); return {"total": 0}
            def _fetch_all(self, statement, parameters):
                self.statements.append((statement, parameters)); return []

        repository = RecordingRepository()
        rows, total = repository.list_equities(None, 1, 25)

        self.assertEqual(([], 0), (rows, total))
        self.assertTrue(all("%s::text IS NULL" in statement for statement, _ in repository.statements))
        self.assertTrue(all(parameters[0] is None for _, parameters in repository.statements))

    def test_all_equities_query_is_complete_and_deterministic(self):
        class RecordingRepository(PostgresAdminPipelineRepository):
            def __init__(self): self.statement = None
            def _fetch_all(self, statement, parameters):
                self.statement = (statement, parameters); return []

        repository = RecordingRepository()
        self.assertEqual([], repository.list_all_equities())
        self.assertIn("WHERE series = 'EQ'", repository.statement[0])
        self.assertIn("ORDER BY symbol, isin", repository.statement[0])
        self.assertNotIn("LIMIT", repository.statement[0])

    def test_interrupted_item_update_qualifies_columns_shared_with_run_table(self):
        class RecordingCursor:
            def __init__(self): self.statements = []
            def execute(self, statement, parameters=None): self.statements.append(statement)
            def fetchall(self): return []
            def __enter__(self): return self
            def __exit__(self, *_): return False

        class RecordingConnection:
            def __init__(self): self.recording_cursor = RecordingCursor()
            def cursor(self): return self.recording_cursor
            def commit(self): pass
            def __enter__(self): return self
            def __exit__(self, *_): return False

        class RecordingRepository(PostgresAdminPipelineRepository):
            def __init__(self): self.connection = RecordingConnection()
            def _connect(self): return self.connection

        repository = RecordingRepository()
        repository.fail_interrupted_pipeline_runs()

        item_update = repository.connection.recording_cursor.statements[0]
        self.assertIn("COALESCE(item.error_message", item_update)
        self.assertIn("COALESCE(item.finished_at", item_update)


if __name__ == "__main__":
    unittest.main()
