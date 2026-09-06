"""Admin-only orchestration for selected-security full pipeline runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from threading import Thread
from typing import Protocol

from data_pipeline.history_backfill import BackfillRequest, HistoryBackfillService
from pattern_engine.enums import ImportStatus
from pattern_engine.runner import PatternEngineVersions


class AdminPipelineRepository(Protocol):
    def list_equities(self, search: str | None, page: int, page_size: int) -> tuple[list[dict[str, object]], int]: ...
    def list_all_equities(self) -> list[dict[str, object]]: ...
    def get_equities(self, isins: Sequence[str]) -> list[dict[str, object]]: ...
    def create_pipeline_run(self, values: Mapping[str, object], securities: Sequence[Mapping[str, object]]) -> str: ...
    def update_pipeline_run(self, run_id: str, status: str, **values: object) -> None: ...
    def pipeline_run_status(self, run_id: str) -> str | None: ...
    def pause_pipeline_run(self, run_id: str) -> bool: ...
    def terminate_pipeline_run(self, run_id: str) -> bool: ...
    def prepare_pipeline_run_resume(self, run_id: str) -> list[dict[str, object]]: ...
    def update_pipeline_item(self, run_id: str, isin: str, status: str, stage: str, **values: object) -> None: ...
    def get_pipeline_run(self, run_id: str, item_page: int, item_page_size: int) -> dict[str, object] | None: ...
    def list_pipeline_runs(self, page: int, page_size: int) -> tuple[list[dict[str, object]], int]: ...


class AdminPipelineService:
    """Run source import through pattern persistence for explicitly selected equities."""

    MAX_SELECTION = 100
    DEFAULT_BATCH_SIZE = 25
    MAX_BATCH_SIZE = 100

    def __init__(
        self,
        repository: AdminPipelineRepository,
        history_service: HistoryBackfillService,
        recovery_service,
        configuration,
        *,
        executor: Callable[[Callable[[], None]], None] | None = None,
        today: Callable[[], date] = date.today,
        logger=None,
        max_workers: int = 3,
    ) -> None:
        if not 1 <= max_workers <= 8:
            raise ValueError("max_workers must be between 1 and 8")
        self._repository = repository
        self._history = history_service
        self._recovery = recovery_service
        self._configuration = configuration
        self._executor = executor or self._start_thread
        self._today = today
        self._logger = logger
        self._max_workers = max_workers

    def list_equities(self, query: Mapping[str, list[str]]) -> dict[str, object]:
        page = _bounded_integer(_one(query, "page"), 1, 1, 100_000, "page")
        page_size = _bounded_integer(_one(query, "pageSize"), 25, 10, 100, "pageSize")
        search = (_one(query, "search") or "").strip() or None
        rows, total = self._repository.list_equities(search, page, page_size)
        return {
            "items": [_equity_payload(row) for row in rows],
            "page": page,
            "pageSize": page_size,
            "totalItems": total,
            "totalPages": (total + page_size - 1) // page_size,
        }

    def list_runs(self, query: Mapping[str, list[str]]) -> dict[str, object]:
        page = _bounded_integer(_one(query, "page"), 1, 1, 100_000, "page")
        page_size = _bounded_integer(_one(query, "pageSize"), 10, 5, 50, "pageSize")
        rows, total = self._repository.list_pipeline_runs(page, page_size)
        return {
            "items": [_run_payload(row, include_items=False) for row in rows],
            "page": page, "pageSize": page_size, "totalItems": total,
            "totalPages": (total + page_size - 1) // page_size,
        }

    def get_run(self, run_id: str, query: Mapping[str, list[str]] | None = None) -> dict[str, object]:
        query = query or {}
        item_page = _bounded_integer(_one(query, "itemPage"), 1, 1, 100_000, "itemPage")
        item_page_size = _bounded_integer(
            _one(query, "itemPageSize"), 25, 10, 100, "itemPageSize"
        )
        run = self._repository.get_pipeline_run(run_id, item_page, item_page_size)
        if run is None:
            raise LookupError("Pipeline run not found")
        return {
            "run": _run_payload(
                run, include_items=True, item_page=item_page, item_page_size=item_page_size
            )
        }

    def start(self, payload: Mapping[str, object], requested_by: str) -> dict[str, object]:
        raw_isins = payload.get("isins")
        run_all = payload.get("allEquities") is True
        if raw_isins is None:
            raw_isins = []
        if not isinstance(raw_isins, list):
            raise ValueError("isins must be an array")
        isins = tuple(dict.fromkeys(
            str(value).strip().upper() for value in raw_isins if str(value).strip()
        ))
        if run_all and isins:
            raise ValueError("Run all cannot be combined with selected equities")
        if not run_all and not isins:
            raise ValueError("Select at least one equity or choose Run all equities")
        if not run_all and len(isins) > self.MAX_SELECTION:
            raise ValueError(f"Select at most {self.MAX_SELECTION} equities per run")
        batch_size = _bounded_integer(
            payload.get("batchSize"), self.DEFAULT_BATCH_SIZE, 1,
            self.MAX_BATCH_SIZE, "batchSize",
        )
        to_date = _as_date(payload.get("toDate"), self._today())
        years = int(self._configuration.section("data")["initial_history_years"])
        from_date = _as_date(payload.get("fromDate"), _years_before(to_date, years))
        if from_date > to_date:
            raise ValueError("fromDate cannot be after toDate")
        if run_all:
            ordered = self._repository.list_all_equities()
            if not ordered:
                raise ValueError("No eligible equities are available to run")
        else:
            securities = self._repository.get_equities(isins)
            found = {str(row["isin"]) for row in securities}
            missing = [isin for isin in isins if isin not in found]
            if missing:
                raise ValueError(f"Unknown or ineligible equities: {', '.join(missing[:10])}")
            by_isin = {str(row["isin"]): row for row in securities}
            ordered = [by_isin[isin] for isin in isins]
        versions = self._versions()
        values = {
            "requested_by": requested_by,
            "requested_from_date": from_date,
            "requested_to_date": to_date,
            "versions": {
                "engine": versions.engine,
                "feature": versions.feature,
                "adjustment": versions.adjustment,
            },
            "force_refresh": bool(payload.get("forceRefresh", False)),
            "run_scope": "ALL" if run_all else "SELECTION",
            "batch_size": batch_size,
            "status": "PENDING",
        }
        run_id = self._repository.create_pipeline_run(values, ordered)
        self._executor(lambda: self._execute(
            run_id, ordered, from_date, to_date, versions,
            values["force_refresh"], batch_size,
        ))
        return self.get_run(run_id)

    def pause(self, run_id: str) -> dict[str, object]:
        run = self._require_run(run_id)
        if run["status"] not in {"PENDING", "RUNNING"}:
            raise ValueError(f"A {run['status']} pipeline run cannot be paused")
        if not self._repository.pause_pipeline_run(run_id):
            raise ValueError("Pipeline status changed; reload and try again")
        return self.get_run(run_id)

    def terminate(self, run_id: str) -> dict[str, object]:
        run = self._require_run(run_id)
        if run["status"] not in {"PENDING", "RUNNING", "PAUSED"}:
            raise ValueError(f"A {run['status']} pipeline run cannot be terminated")
        if not self._repository.terminate_pipeline_run(run_id):
            raise ValueError("Pipeline status changed; reload and try again")
        return self.get_run(run_id)

    def resume(self, run_id: str) -> dict[str, object]:
        run = self._require_run(run_id)
        if run["status"] not in {"FAILED", "PARTIAL", "PAUSED"}:
            raise ValueError(f"A {run['status']} pipeline run cannot be resumed")
        securities = self._repository.prepare_pipeline_run_resume(run_id)
        if not securities:
            raise ValueError("The pipeline has no unfinished equities to resume")
        versions = run.get("versions") or {}
        version_set = PatternEngineVersions(
            str(versions["engine"]), str(versions["feature"]), str(versions["adjustment"])
        )
        completed = int(run.get("securities_completed") or 0)
        self._executor(lambda: self._execute(
            run_id,
            securities,
            run["requested_from_date"],
            run["requested_to_date"],
            version_set,
            bool(run.get("force_refresh")),
            int(run.get("batch_size") or self.DEFAULT_BATCH_SIZE),
            completed=completed,
        ))
        return self.get_run(run_id)

    def _require_run(self, run_id):
        run = self._repository.get_pipeline_run(run_id, 1, 1)
        if run is None:
            raise LookupError("Pipeline run not found")
        return run

    def _execute(
        self, run_id, securities, from_date, to_date, versions, force_refresh,
        batch_size, *, completed=0,
    ):
        failed = 0
        errors = []
        if self._repository.pipeline_run_status(run_id) in {"PAUSED", "TERMINATED"}:
            return
        self._repository.update_pipeline_run(run_id, "RUNNING", started=True)
        with ThreadPoolExecutor(
            max_workers=self._max_workers, thread_name_prefix="admin-pipeline-equity"
        ) as pool:
            for batch in _batches(securities, batch_size):
                if self._repository.pipeline_run_status(run_id) in {"PAUSED", "TERMINATED"}:
                    return
                futures = {
                    pool.submit(
                        self._process_security,
                        run_id, security, from_date, to_date, versions, force_refresh,
                    ): security
                    for security in batch
                }
                for future in as_completed(futures):
                    outcome = future.result()
                    if outcome is None:
                        continue
                    succeeded, symbol, message = outcome
                    if succeeded:
                        completed += 1
                    else:
                        failed += 1
                        errors.append(f"{symbol}: {message}")
                    control_status = self._repository.pipeline_run_status(run_id)
                    parent_status = (
                        control_status if control_status in {"PAUSED", "TERMINATED"} else "RUNNING"
                    )
                    self._repository.update_pipeline_run(
                        run_id, parent_status,
                        securities_completed=completed, securities_failed=failed,
                    )
                if self._repository.pipeline_run_status(run_id) in {"PAUSED", "TERMINATED"}:
                    return
        status = "PARTIAL" if completed and failed else "FAILED" if failed else "COMPLETED"
        self._repository.update_pipeline_run(
            run_id, status, securities_completed=completed, securities_failed=failed,
            error_summary="; ".join(errors[:20]) or None, finished=True,
        )
        if self._logger:
            self._logger.emit(
                "admin_pipeline_completed", level="ERROR" if failed else "INFO",
                job_type="ADMIN_FULL_PIPELINE", source_status=status,
                row_count=completed, details={"adminPipelineRunId": run_id, "failed": failed},
            )

    def _process_security(
        self, run_id, security, from_date, to_date, versions, force_refresh,
    ):
        if self._repository.pipeline_run_status(run_id) in {"PAUSED", "TERMINATED"}:
            return None
        isin, symbol = str(security["isin"]), str(security["symbol"])
        self._repository.update_pipeline_item(
            run_id, isin, "RUNNING", "SOURCE_IMPORT", started=True
        )
        try:
            imported = self._history.run(BackfillRequest(
                from_date=from_date, to_date=to_date, isin=isin,
                batch_size=1, force=force_refresh, initiated_by="manual",
            ))
            item = imported.securities[0] if imported.securities else None
            if imported.status not in {ImportStatus.COMPLETED, None} or item is None or item.error:
                raise RuntimeError(
                    item.error if item and item.error else "Source import did not complete"
                )
            self._repository.update_pipeline_item(
                run_id, isin, "RUNNING", "ADJUST_FEATURE_SCAN",
                history_run_id=imported.run_id, rows_downloaded=item.rows_downloaded,
            )
            rebuilt = self._recovery.rebuild_security(
                isin, from_date, to_date, versions, dry_run=False
            )
            if rebuilt.get("status") != "COMPLETED":
                raise RuntimeError(f"Pattern scan finished with {rebuilt.get('status')}")
            self._repository.update_pipeline_item(
                run_id, isin, "COMPLETED", "COMPLETED",
                history_run_id=imported.run_id, pattern_run_id=rebuilt.get("runId"),
                rows_downloaded=item.rows_downloaded,
                candidates_detected=int(
                    (rebuilt.get("metrics") or {}).get("candidatesDetected") or 0
                ),
                finished=True,
            )
            return True, symbol, None
        except Exception as error:  # one equity must not abort its batch
            message = str(error).replace("\n", " ")[:1000]
            self._repository.update_pipeline_item(
                run_id, isin, "FAILED", "FAILED", error_message=message, finished=True
            )
            return False, symbol, message

    def _versions(self):
        adjustment = str(self._configuration.section("adjustments")["methodology_version"])
        return PatternEngineVersions(
            self._configuration.version,
            self._configuration.version,
            adjustment,
        )

    @staticmethod
    def _start_thread(action):
        Thread(target=action, name="admin-full-pipeline", daemon=True).start()


class DisabledAdminPipelineService:
    """Safe fallback for dependency-injected HTTP tests without market storage."""

    def list_equities(self, query): return {"items": [], "page": 1, "pageSize": 25, "totalItems": 0, "totalPages": 0}
    def list_runs(self, query): return {"items": [], "page": 1, "pageSize": 10, "totalItems": 0, "totalPages": 0}
    def get_run(self, run_id, query=None): raise LookupError("Pipeline run not found")
    def start(self, payload, requested_by): raise RuntimeError("Admin pipeline is not configured")
    def pause(self, run_id): raise RuntimeError("Admin pipeline is not configured")
    def resume(self, run_id): raise RuntimeError("Admin pipeline is not configured")
    def terminate(self, run_id): raise RuntimeError("Admin pipeline is not configured")


def _equity_payload(row):
    return {
        "isin": row.get("isin"), "symbol": row.get("symbol"),
        "companyName": row.get("company_name"), "series": row.get("series"),
        "listedOn": row.get("listed_on"), "latestRawDate": row.get("latest_raw_date"),
        "lastPipelineStatus": row.get("last_pipeline_status"),
        "lastPipelineAt": row.get("last_pipeline_at"),
    }


def _run_payload(row, *, include_items, item_page=1, item_page_size=25):
    result = {
        "runId": row.get("id"), "status": row.get("status"),
        "fromDate": row.get("requested_from_date"), "toDate": row.get("requested_to_date"),
        "versions": row.get("versions") or {}, "forceRefresh": bool(row.get("force_refresh")),
        "runScope": row.get("run_scope") or "SELECTION",
        "batchSize": row.get("batch_size") or AdminPipelineService.DEFAULT_BATCH_SIZE,
        "securitiesTotal": row.get("securities_total", 0),
        "securitiesCompleted": row.get("securities_completed", 0),
        "securitiesFailed": row.get("securities_failed", 0),
        "errorSummary": row.get("error_summary"), "createdAt": row.get("created_at"),
        "startedAt": row.get("started_at"), "finishedAt": row.get("finished_at"),
        "pausedAt": row.get("paused_at"), "terminatedAt": row.get("terminated_at"),
        "lastResumedAt": row.get("last_resumed_at"),
        "resumeCount": row.get("resume_count", 0),
    }
    if include_items:
        result["items"] = [{
            "isin": item.get("isin"), "symbol": item.get("symbol"),
            "status": item.get("status"), "currentStage": item.get("current_stage"),
            "historyRunId": item.get("history_run_id"), "patternRunId": item.get("pattern_run_id"),
            "rowsDownloaded": item.get("rows_downloaded", 0),
            "candidatesDetected": item.get("candidates_detected", 0),
            "error": item.get("error_message"), "startedAt": item.get("started_at"),
            "finishedAt": item.get("finished_at"),
            "attemptCount": item.get("attempt_count", 0),
        } for item in row.get("items", [])]
        result["itemPage"] = item_page
        result["itemPageSize"] = item_page_size
        result["itemTotalPages"] = (
            (int(row.get("securities_total") or 0) + item_page_size - 1) // item_page_size
        )
    return result


def _one(query, name): return query.get(name, [None])[-1]
def _bounded_integer(value, default, minimum, maximum, name):
    try: parsed = default if value in (None, "") else int(value)
    except (TypeError, ValueError) as error: raise ValueError(f"{name} must be an integer") from error
    if not minimum <= parsed <= maximum: raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed
def _as_date(value, default):
    if value in (None, ""): return default
    try: return date.fromisoformat(str(value))
    except ValueError as error: raise ValueError("Dates must use YYYY-MM-DD") from error
def _years_before(value, years):
    try: return value.replace(year=value.year - years)
    except ValueError: return value.replace(year=value.year - years, month=2, day=28)


def _batches(values, batch_size):
    for offset in range(0, len(values), batch_size):
        yield values[offset:offset + batch_size]
