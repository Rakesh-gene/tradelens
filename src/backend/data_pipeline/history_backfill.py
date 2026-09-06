"""Resumable, observable initial history import orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Iterable, Mapping
from time import perf_counter

from data_pipeline.normalization import corporate_action_record, raw_bar_record
from data_pipeline.nse_api import NseApiClient
from pattern_engine.enums import ImportJobType, ImportStatus
from repositories.market_data import MarketDataRepository


ELIGIBLE_SERIES = frozenset({"EQ"})
LONG_GAP_DAYS = 7
ACTION_REPAIR_DAYS = 20


@dataclass(frozen=True, slots=True)
class BackfillRequest:
    from_date: date
    to_date: date
    symbol: str | None = None
    isin: str | None = None
    batch_size: int = 100
    max_securities: int | None = None
    resume: bool = False
    retry_failed: bool = False
    force: bool = False
    dry_run: bool = False
    initiated_by: str = "manual"


@dataclass(slots=True)
class SecurityBackfillResult:
    isin: str
    symbol: str
    requested_from_date: date
    requested_to_date: date
    chunks: list[tuple[date, date]]
    rows_downloaded: int = 0
    rows_inserted: int = 0
    actions_inserted: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BackfillRunResult:
    run_id: str | None
    status: ImportStatus | None
    securities: tuple[SecurityBackfillResult, ...]


class HistoryBackfillService:
    """Coordinates history and action imports without leaking NSE rules to storage."""

    def __init__(
        self,
        repository: MarketDataRepository,
        nse_client: NseApiClient | None = None,
        *,
        event_logger=None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._repository = repository
        self._nse_client = nse_client or NseApiClient()
        self._event_logger = event_logger
        self._today = today

    def plan(self, request: BackfillRequest) -> list[SecurityBackfillResult]:
        """Return eligible-security ranges using only repository reads."""

        self._validate_request(request)
        securities = self._eligible_securities(request)
        return [self._plan_security(security, request) for security in securities]

    def run(self, request: BackfillRequest) -> BackfillRunResult:
        started = perf_counter()
        plans = self.plan(request)
        if request.dry_run:
            return BackfillRunResult(None, None, tuple(plans))

        if request.resume:
            self._mark_interrupted_runs()

        run_id = self._repository.create_import_run(
            ImportJobType.HISTORY_BACKFILL,
            request.initiated_by,
            requested_from_date=request.from_date,
            requested_to_date=request.to_date,
            configuration={
                "eligible_series": sorted(ELIGIBLE_SERIES),
                "max_chunk_span": "one_year",
                "resume": request.resume,
                "retry_failed": request.retry_failed,
                "force": request.force,
            },
            securities_total=len(plans),
        )
        self._repository.update_import_run(run_id, ImportStatus.RUNNING)

        completed = failed = downloaded = inserted = rejected = 0
        results: list[SecurityBackfillResult] = []
        for batch in _batches(plans, request.batch_size):
            for plan in batch:
                security_started = perf_counter(); error_class = None
                attempt = int((self._repository.get_import_checkpoint(ImportJobType.HISTORY_BACKFILL, plan.isin) or {}).get("retry_count") or 0) + 1
                try:
                    self._import_security(plan, run_id)
                    completed += 1
                    downloaded += plan.rows_downloaded
                    inserted += plan.rows_inserted + plan.actions_inserted
                except Exception as error:  # a failed security must not abort the universe
                    error_class = type(error).__name__
                    plan.error = self._error_summary(error)
                    failed += 1
                    rejected += 1
                    self._record_failure(plan, run_id)
                if self._event_logger:
                    self._event_logger.emit(
                        "history_security_completed" if not plan.error else "history_security_failed",
                        level="INFO" if not plan.error else "ERROR", run_id=run_id,
                        job_type=ImportJobType.HISTORY_BACKFILL.value, isin=plan.isin, symbol=plan.symbol,
                        requested_from_date=plan.requested_from_date, requested_to_date=plan.requested_to_date,
                        attempt=attempt,
                        duration_ms=round((perf_counter() - security_started) * 1000),
                        row_count=plan.rows_downloaded, source_status="OK" if not plan.error else "FAILED",
                        error_class=error_class, details={"error": plan.error} if plan.error else {},
                    )
                results.append(plan)
                self._repository.update_import_run(
                    run_id,
                    ImportStatus.RUNNING,
                    securities_completed=completed,
                    securities_failed=failed,
                    rows_downloaded=downloaded,
                    rows_inserted=inserted,
                    rows_rejected=rejected,
                )

        status = ImportStatus.PARTIAL if failed else ImportStatus.COMPLETED
        errors = [f"{result.isin}: {result.error}" for result in results if result.error]
        warnings = [warning for result in results for warning in result.warnings]
        summary = "; ".join((errors + warnings)[:20]) or None
        self._repository.update_import_run(
            run_id,
            status,
            securities_completed=completed,
            securities_failed=failed,
            rows_downloaded=downloaded,
            rows_inserted=inserted,
            rows_rejected=rejected,
            error_summary=summary,
            duration_ms=round((perf_counter() - started) * 1000),
            source_metrics=getattr(self._nse_client, "metrics", {}),
        )
        return BackfillRunResult(run_id, status, tuple(results))

    def _eligible_securities(self, request: BackfillRequest) -> list[dict[str, object]]:
        requested_symbol = self._normalize_optional(request.symbol)
        requested_isin = self._normalize_optional(request.isin)
        if requested_symbol and requested_isin:
            raise ValueError("Specify at most one of symbol and isin")
        securities = []
        for security in self._repository.list_eligible_securities():
            series = str(security.get("series") or "").strip().upper()
            symbol = self._normalize_optional(str(security.get("symbol") or ""))
            isin = self._normalize_optional(str(security.get("isin") or ""))
            if not symbol or not isin or series not in ELIGIBLE_SERIES:
                continue
            if requested_symbol and symbol != requested_symbol:
                continue
            if requested_isin and isin != requested_isin:
                continue
            if request.retry_failed:
                checkpoint = self._repository.get_import_checkpoint(
                    ImportJobType.HISTORY_BACKFILL, isin
                )
                if (checkpoint or {}).get("status") != ImportStatus.FAILED.value:
                    continue
            securities.append(dict(security, symbol=symbol, isin=isin, series=series))
        securities.sort(key=lambda security: str(security["isin"]))
        if request.max_securities is not None:
            return securities[:request.max_securities]
        return securities

    def _plan_security(self, security: Mapping[str, object], request: BackfillRequest) -> SecurityBackfillResult:
        isin, symbol = str(security["isin"]), str(security["symbol"])
        listed_on = security.get("listed_on")
        lower_bound = max(request.from_date, listed_on) if isinstance(listed_on, date) else request.from_date
        if lower_bound > request.to_date:
            return SecurityBackfillResult(isin, symbol, lower_bound, request.to_date, [])
        existing_min, existing_max = self._repository.get_raw_bar_date_range(isin)
        checkpoint = self._repository.get_import_checkpoint(ImportJobType.HISTORY_BACKFILL, isin)
        completed_range = not request.force and self._checkpoint_covers(checkpoint, lower_bound, request.to_date)
        missing_ranges = [] if completed_range else self._missing_ranges(
            lower_bound, request.to_date, existing_min, existing_max
        )
        chunks = [chunk for period in missing_ranges for chunk in self._split_chunks(*period)]
        return SecurityBackfillResult(isin, symbol, lower_bound, request.to_date, chunks)

    def _import_security(self, result: SecurityBackfillResult, run_id: str) -> None:
        all_dates: list[date] = []
        for chunk_from, chunk_to in result.chunks:
            bars = self._nse_client.fetch_equity_history(result.symbol, chunk_from, chunk_to)
            bars_by_date = {bar.trading_date: bar for bar in bars}
            ordered_bars = [bars_by_date[trading_date] for trading_date in sorted(bars_by_date)]
            self._validate_bars(result, ordered_bars, chunk_from, chunk_to)
            raw_bars = [
                raw_bar_record(bar, result.isin, run_id, expected_symbol=result.symbol)
                for bar in ordered_bars
            ]
            self._repository.persist_history_chunk(
                raw_bars,
                self._successful_checkpoint(
                    ImportJobType.HISTORY_BACKFILL,
                    result.isin,
                    chunk_from,
                    chunk_to,
                    ordered_bars,
                    run_id,
                ),
            )
            result.rows_downloaded += len(ordered_bars)
            result.rows_inserted += len(raw_bars)
            all_dates.extend(bar.trading_date for bar in ordered_bars)

        action_checkpoint = self._repository.get_import_checkpoint(
            ImportJobType.CORPORATE_ACTION_BACKFILL, result.isin
        )
        if not self._checkpoint_covers(action_checkpoint, result.requested_from_date, result.requested_to_date):
            action_from = self._action_refresh_start(
                action_checkpoint, result.requested_from_date
            )
            actions = self._nse_client.fetch_corporate_actions(
                result.symbol, action_from, result.requested_to_date
            )
            mapped_actions = [
                corporate_action_record(
                    action, result.isin, run_id, expected_symbol=result.symbol
                )
                for action in actions
            ]
            result.actions_inserted = self._repository.upsert_corporate_actions(mapped_actions)
            self._repository.upsert_import_checkpoint(self._successful_checkpoint(
                ImportJobType.CORPORATE_ACTION_BACKFILL,
                result.isin,
                self._continuous_coverage_start(
                    action_checkpoint, result.requested_from_date
                ),
                result.requested_to_date,
                (),
                run_id,
            ))
        if all_dates:
            self._report_long_gaps(result, sorted(set(all_dates)))

    @staticmethod
    def _action_refresh_start(
        checkpoint: Mapping[str, object] | None, requested_from: date
    ) -> date:
        """Use a short overlap to catch recent NSE action corrections."""

        if checkpoint and checkpoint.get("status") == ImportStatus.COMPLETED.value:
            attempted_to = checkpoint.get("last_attempted_to_date")
            if isinstance(attempted_to, date):
                return max(requested_from, attempted_to - timedelta(days=ACTION_REPAIR_DAYS))
        return requested_from

    @staticmethod
    def _continuous_coverage_start(
        checkpoint: Mapping[str, object] | None, requested_from: date
    ) -> date:
        if checkpoint and checkpoint.get("status") == ImportStatus.COMPLETED.value:
            attempted_from = checkpoint.get("last_attempted_from_date")
            if isinstance(attempted_from, date):
                return min(requested_from, attempted_from)
        return requested_from

    @staticmethod
    def _missing_ranges(
        start: date, end: date, existing_min: date | None, existing_max: date | None
    ) -> list[tuple[date, date]]:
        if existing_min is None or existing_max is None:
            return [(start, end)]
        ranges: list[tuple[date, date]] = []
        if start < existing_min:
            ranges.append((start, min(end, existing_min - timedelta(days=1))))
        if end > existing_max:
            ranges.append((max(start, existing_max + timedelta(days=1)), end))
        return [(range_start, range_end) for range_start, range_end in ranges if range_start <= range_end]

    @staticmethod
    def _checkpoint_covers(checkpoint: Mapping[str, object] | None, start: date, end: date) -> bool:
        if not checkpoint or checkpoint.get("status") != ImportStatus.COMPLETED.value:
            return False
        attempted_from = checkpoint.get("last_attempted_from_date")
        attempted_to = checkpoint.get("last_attempted_to_date")
        return isinstance(attempted_from, date) and isinstance(attempted_to, date) and attempted_from <= start and attempted_to >= end

    @staticmethod
    def _split_chunks(start: date, end: date) -> Iterable[tuple[date, date]]:
        current = start
        while current <= end:
            chunk_end = min(end, _add_year(current) - timedelta(days=1))
            yield current, chunk_end
            current = chunk_end + timedelta(days=1)

    @staticmethod
    def _successful_checkpoint(
        job_type: ImportJobType, isin: str, attempted_from: date, attempted_to: date,
        bars: Iterable[object], run_id: str,
    ) -> dict[str, object]:
        dates = [bar.trading_date for bar in bars]
        return {
            "job_type": job_type,
            "isin": isin,
            "earliest_successful_trading_date": min(dates) if dates else None,
            "latest_successful_trading_date": max(dates) if dates else None,
            "last_attempted_from_date": attempted_from,
            "last_attempted_to_date": attempted_to,
            "status": ImportStatus.COMPLETED,
            "retry_count": 0,
            "last_error": None,
            "last_successful_run_id": run_id,
        }

    def _record_failure(self, result: SecurityBackfillResult, run_id: str) -> None:
        checkpoint = self._repository.get_import_checkpoint(ImportJobType.HISTORY_BACKFILL, result.isin) or {}
        self._repository.upsert_import_checkpoint({
            "job_type": ImportJobType.HISTORY_BACKFILL,
            "isin": result.isin,
            "last_attempted_from_date": result.requested_from_date,
            "last_attempted_to_date": result.requested_to_date,
            "status": ImportStatus.FAILED,
            "retry_count": int(checkpoint.get("retry_count") or 0) + 1,
            "last_error": result.error,
            "last_successful_run_id": None,
        })

    @staticmethod
    def _validate_bars(result: SecurityBackfillResult, bars: list[object], start: date, end: date) -> None:
        for bar in bars:
            if bar.trading_date < start or bar.trading_date > end:
                raise ValueError(f"received bar outside requested range: {bar.trading_date}")
            if bar.trading_date.weekday() >= 5:
                result.warnings.append(f"{result.isin}: NSE supplied weekend bar {bar.trading_date}")

    @staticmethod
    def _report_long_gaps(result: SecurityBackfillResult, dates: list[date]) -> None:
        for prior, current in zip(dates, dates[1:]):
            if (current - prior).days > LONG_GAP_DAYS:
                result.warnings.append(f"{result.isin}: source gap from {prior} to {current}")

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        normalized = " ".join((value or "").strip().upper().split())
        return normalized or None

    def _validate_request(self, request: BackfillRequest) -> None:
        if request.from_date > request.to_date:
            raise ValueError("from_date cannot be after to_date")
        if request.to_date > self._today():
            raise ValueError("to_date cannot be in the future")
        if request.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if request.max_securities is not None and request.max_securities <= 0:
            raise ValueError("max_securities must be positive")

    def _mark_interrupted_runs(self) -> None:
        marker = getattr(self._repository, "mark_interrupted_import_runs", None)
        if callable(marker):
            marker(ImportJobType.HISTORY_BACKFILL)

    @staticmethod
    def _error_summary(error: Exception) -> str:
        return str(error).replace("\n", " ")[:500] or error.__class__.__name__


def _add_year(value: date) -> date:
    try:
        return value.replace(year=value.year + 1)
    except ValueError:  # 29 February
        return value.replace(year=value.year + 1, month=2, day=28)


def _batches(items: list[SecurityBackfillResult], batch_size: int) -> Iterable[list[SecurityBackfillResult]]:
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]
