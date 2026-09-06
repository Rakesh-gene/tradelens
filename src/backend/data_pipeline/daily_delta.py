"""Incremental NSE EOD import with a bounded repair window."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Mapping
from time import perf_counter

from data_pipeline.models import NseEquityHistoryRecord
from data_pipeline.normalization import corporate_action_record, parse_eod_report, raw_bar_record
from data_pipeline.nse_api import NseApiClient, NseRequestError
from pattern_engine.enums import ImportJobType, ImportStatus
from repositories.market_data import MarketDataRepository


@dataclass(frozen=True, slots=True)
class DailyDeltaRequest:
    as_of: date
    repair_sessions: int = 10
    symbol: str | None = None
    isin: str | None = None
    max_securities: int | None = None
    dry_run: bool = False
    initiated_by: str = "scheduler"


@dataclass(slots=True)
class SecurityDeltaResult:
    isin: str
    symbol: str
    from_date: date
    to_date: date
    rows_downloaded: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    actions_inserted: int = 0
    changed_from_date: date | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DailyDeltaRunResult:
    run_id: str | None
    status: ImportStatus | None
    latest_session: date | None
    securities: tuple[SecurityDeltaResult, ...]


class DailyDeltaService:
    """Imports only the latest completed session plus a bounded repair window."""

    def __init__(
        self,
        repository: MarketDataRepository,
        nse_client: NseApiClient | None = None,
        *,
        session_resolver: Callable[[date, Mapping[str, Mapping[str, object]]], tuple[date, dict[str, NseEquityHistoryRecord]]] | None = None,
        on_source_commit: Callable[[str, date, date], None] | None = None,
        event_logger=None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._repository = repository
        self._nse_client = nse_client or NseApiClient()
        self._session_resolver = session_resolver
        self._on_source_commit = on_source_commit
        self._event_logger = event_logger
        self._today = today

    def run(self, request: DailyDeltaRequest) -> DailyDeltaRunResult:
        started = perf_counter()
        self._validate_request(request)
        securities = self._eligible_securities(request)
        security_map = {str(item["isin"]): item for item in securities}
        if not security_map:
            return DailyDeltaRunResult(None, ImportStatus.COMPLETED, None, ())
        latest_session, bulk_bars = self._latest_completed_session(request.as_of, security_map)
        results = [self._plan_security(item, latest_session, request.repair_sessions) for item in securities]
        if request.dry_run:
            return DailyDeltaRunResult(None, None, latest_session, tuple(results))

        run_id = self._repository.create_import_run(
            ImportJobType.DAILY_DELTA,
            request.initiated_by,
            requested_from_date=min(item.from_date for item in results),
            requested_to_date=latest_session,
            configuration={"repair_sessions": request.repair_sessions, "bulk_eod": bool(bulk_bars)},
            securities_total=len(results),
        )
        self._repository.update_import_run(run_id, ImportStatus.RUNNING)
        completed = failed = downloaded = inserted = updated = rejected = 0
        for result in results:
            security_started = perf_counter(); error_class = None
            attempt = int((self._repository.get_import_checkpoint(ImportJobType.DAILY_DELTA, result.isin) or {}).get("retry_count") or 0) + 1
            try:
                self._import_security(result, latest_session, bulk_bars, run_id)
                completed += 1
                downloaded += result.rows_downloaded
                inserted += result.rows_inserted + result.actions_inserted
                updated += result.rows_updated
            except Exception as error:  # one bad security must not stop the daily run
                error_class = type(error).__name__
                result.error = str(error).replace("\n", " ")[:500]
                failed += 1
                rejected += 1
                self._record_failure(result, latest_session, run_id)
            if self._event_logger:
                self._event_logger.emit(
                    "daily_security_completed" if not result.error else "daily_security_failed",
                    level="INFO" if not result.error else "ERROR", run_id=run_id,
                    job_type=ImportJobType.DAILY_DELTA.value, isin=result.isin, symbol=result.symbol,
                    requested_from_date=result.from_date, requested_to_date=result.to_date,
                    attempt=attempt,
                    duration_ms=round((perf_counter() - security_started) * 1000),
                    row_count=result.rows_downloaded, source_status="OK" if not result.error else "FAILED",
                    error_class=error_class, details={"error": result.error} if result.error else {},
                )
            self._repository.update_import_run(
                run_id,
                ImportStatus.RUNNING,
                securities_completed=completed,
                securities_failed=failed,
                rows_downloaded=downloaded,
                rows_inserted=inserted,
                rows_updated=updated,
                rows_rejected=rejected,
            )
        status = ImportStatus.PARTIAL if failed else ImportStatus.COMPLETED
        summary = "; ".join(f"{item.isin}: {item.error}" for item in results if item.error) or None
        self._repository.update_import_run(
            run_id, status, securities_completed=completed, securities_failed=failed,
            rows_downloaded=downloaded, rows_inserted=inserted, rows_updated=updated,
            rows_rejected=rejected, error_summary=summary,
            duration_ms=round((perf_counter() - started) * 1000),
            source_metrics=getattr(self._nse_client, "metrics", {}),
        )
        return DailyDeltaRunResult(run_id, status, latest_session, tuple(results))

    def _latest_completed_session(
        self, as_of: date, securities: Mapping[str, Mapping[str, object]]
    ) -> tuple[date, dict[str, NseEquityHistoryRecord]]:
        if self._session_resolver:
            return self._session_resolver(as_of, securities)
        for days_back in range(0, 11):
            candidate = as_of - timedelta(days=days_back)
            try:
                payload = self._nse_client.download_eod_report(candidate)
                bars = parse_eod_report(payload, securities)
                if bars:
                    return candidate, bars
            except NseRequestError as error:
                if error.status_code == 404:
                    continue
                raise
        raise RuntimeError("NSE has not published a completed EOD report in the lookback window")

    def _import_security(self, result, latest_session, bulk_bars, run_id) -> None:
        existing = {
            row["trading_date"]: row
            for row in self._repository.load_raw_bars(result.isin, result.from_date, latest_session)
        }
        bulk_bar = bulk_bars.get(result.isin)
        bars = [bulk_bar] if bulk_bar and result.from_date == latest_session else self._nse_client.fetch_equity_history(
            result.symbol, result.from_date, latest_session
        )
        bars = sorted({bar.trading_date: bar for bar in bars}.values(), key=lambda bar: bar.trading_date)
        raw_bars = [
            raw_bar_record(bar, result.isin, run_id, expected_symbol=result.symbol)
            for bar in bars
        ]
        result.rows_downloaded = len(bars)
        result.rows_inserted = sum(1 for bar in raw_bars if bar["trading_date"] not in existing)
        result.rows_updated = sum(
            1 for bar in raw_bars
            if bar["trading_date"] in existing
            and existing[bar["trading_date"]].get("source_checksum") != bar["source_checksum"]
        )
        self._repository.persist_history_chunk(raw_bars, self._checkpoint(
            ImportJobType.DAILY_DELTA, result, bars, run_id, result.from_date, latest_session
        ))
        changed_dates = [
            bar.trading_date for bar in bars
            if existing.get(bar.trading_date, {}).get("source_checksum") != bar.source_checksum
        ]
        if changed_dates:
            result.changed_from_date = min(changed_dates)

        action_start = self._action_start(result.isin, latest_session, result.from_date)
        existing_actions = {
            action["source_event_key"]: action
            for action in self._repository.load_corporate_actions(
                result.isin, action_start, latest_session
            )
        }
        actions = self._nse_client.fetch_corporate_actions(result.symbol, action_start, latest_session)
        mapped = [
            corporate_action_record(
                action, result.isin, run_id, expected_symbol=result.symbol
            )
            for action in actions
        ]
        result.actions_inserted = sum(
            1 for action in mapped if action["source_event_key"] not in existing_actions
        )
        revised_actions = [
            action for action in mapped
            if action["source_event_key"] in existing_actions
            and existing_actions[action["source_event_key"]].get("source_checksum")
            != action["source_checksum"]
        ]
        result.rows_updated += len(revised_actions)
        self._repository.upsert_corporate_actions(mapped)
        self._repository.upsert_import_checkpoint(self._checkpoint(
            ImportJobType.CORPORATE_ACTION_BACKFILL, result, (), run_id, action_start, latest_session
        ))
        changed_actions = [
            action for action in mapped
            if action["source_event_key"] not in existing_actions or action in revised_actions
        ]
        if changed_actions:
            action_date = min(action["ex_date"] for action in changed_actions)
            result.changed_from_date = min(
                value for value in (result.changed_from_date, action_date) if value is not None
            )
        if result.changed_from_date and self._on_source_commit:
            self._on_source_commit(result.isin, result.changed_from_date, latest_session)

    def _action_start(self, isin: str, latest: date, fallback: date) -> date:
        checkpoint = self._repository.get_import_checkpoint(ImportJobType.CORPORATE_ACTION_BACKFILL, isin)
        previous = checkpoint.get("last_attempted_to_date") if checkpoint else None
        return max(fallback, previous - timedelta(days=20)) if isinstance(previous, date) else fallback

    @staticmethod
    def _checkpoint(job_type, result, bars, run_id, attempted_from, attempted_to):
        dates = [bar.trading_date for bar in bars]
        return {
            "job_type": job_type, "isin": result.isin,
            "earliest_successful_trading_date": min(dates) if dates else None,
            "latest_successful_trading_date": max(dates) if dates else None,
            "last_attempted_from_date": attempted_from, "last_attempted_to_date": attempted_to,
            "status": ImportStatus.COMPLETED, "retry_count": 0, "last_error": None,
            "last_successful_run_id": run_id,
        }

    def _record_failure(self, result, latest, run_id):
        self._repository.upsert_import_checkpoint({
            "job_type": ImportJobType.DAILY_DELTA, "isin": result.isin,
            "last_attempted_from_date": result.from_date, "last_attempted_to_date": latest,
            "status": ImportStatus.FAILED, "retry_count": 1, "last_error": result.error,
            "last_successful_run_id": None,
        })

    def _eligible_securities(self, request):
        symbol = self._normalize(request.symbol); isin = self._normalize(request.isin)
        if symbol and isin: raise ValueError("Specify at most one of symbol and isin")
        result = []
        for item in self._repository.list_eligible_securities():
            item_symbol, item_isin = self._normalize(item.get("symbol")), self._normalize(item.get("isin"))
            if str(item.get("series") or "").strip().upper() != "EQ" or not item_symbol or not item_isin: continue
            if symbol and symbol != item_symbol or isin and isin != item_isin: continue
            result.append(dict(item, symbol=item_symbol, isin=item_isin))
        result.sort(key=lambda item: item["isin"])
        return result[:request.max_securities] if request.max_securities else result

    def _plan_security(self, item, latest, repair_sessions):
        listed = item.get("listed_on")
        last = self._repository.get_raw_bar_date_range(item["isin"])[1]
        if last is None:
            start = listed if isinstance(listed, date) else latest
        else:
            search_start = last - timedelta(days=max(30, repair_sessions * 4))
            if isinstance(listed, date):
                search_start = max(search_start, listed)
            recent = self._repository.load_raw_bars(item["isin"], search_start, last)
            sessions = sorted({row["trading_date"] for row in recent if row.get("trading_date") <= last})
            start = sessions[max(0, len(sessions) - repair_sessions - 1)] if sessions else search_start
        return SecurityDeltaResult(item["isin"], item["symbol"], min(start, latest), latest)

    @staticmethod
    def _normalize(value): return " ".join(str(value or "").strip().upper().split()) or None

    def _validate_request(self, request):
        if request.repair_sessions <= 0: raise ValueError("repair_sessions must be positive")
        if request.as_of > self._today(): raise ValueError("as_of cannot be in the future")
        if request.max_securities is not None and request.max_securities <= 0: raise ValueError("max_securities must be positive")
