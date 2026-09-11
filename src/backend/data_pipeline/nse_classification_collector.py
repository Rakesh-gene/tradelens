"""Resumable NSE industry-classification ingestion."""

from __future__ import annotations

from datetime import date
from collections.abc import Mapping
from typing import Protocol

from data_pipeline.nse_api import NseApiClient, NseRequestError
from data_pipeline.normalization import NseDataValidationError


class ClassificationRepository(Protocol):
    def list_classifications_due(self, limit: int | None, stale_days: int) -> list[dict[str, object]]: ...
    def upsert_classification(self, classification: dict[str, object], effective_from: date) -> bool: ...
    def mark_classification_missing(self, isin: str, reason: str) -> None: ...
    def mark_classification_failed(self, isin: str, error: str) -> None: ...


class NseClassificationCollector:
    """Imports NSE's effective-dated four-level company classification."""

    def __init__(self, repository: ClassificationRepository, nse_client: NseApiClient, *, run_repository=None) -> None:
        self._repository = repository
        self._nse_client = nse_client
        self._run_repository = run_repository

    def refresh_new_and_stale(
        self, *, limit: int = 50, stale_days: int = 365,
        effective_from: date | None = None, initiated_by: str = "scheduler",
    ) -> dict[str, object]:
        return self._run(limit, stale_days, effective_from or date.today(), initiated_by)

    def backfill_all(self, *, effective_from: date | None = None, initiated_by: str = "manual") -> dict[str, object]:
        return self._run(None, 0, effective_from or date.today(), initiated_by)

    def refresh_symbols(
        self, symbols: list[str], *, effective_from: date | None = None,
        initiated_by: str = "manual",
    ) -> dict[str, object]:
        wanted = {symbol.strip().upper() for symbol in symbols if symbol.strip()}
        rows = [row for row in self._repository.list_classifications_due(None, 365)
                if str(row["symbol"]).upper() in wanted]
        return self._collect(rows, effective_from or date.today(), initiated_by)

    def _run(self, limit: int | None, stale_days: int, effective_from: date, initiated_by: str) -> dict[str, object]:
        return self._collect(
            self._repository.list_classifications_due(limit, stale_days), effective_from, initiated_by
        )

    def _collect(self, rows, effective_from, initiated_by):
        run_id = None
        if self._run_repository is not None:
            from pattern_engine.enums import ImportJobType, ImportStatus
            run_id = self._run_repository.create_import_run(
                ImportJobType.EQUITY_CLASSIFICATION, initiated_by,
                requested_from_date=effective_from, requested_to_date=effective_from,
                securities_total=len(rows),
            )
            self._run_repository.update_import_run(run_id, ImportStatus.RUNNING)
        completed = changed = missing = failed = 0
        errors: list[str] = []
        for row in rows:
            try:
                record = self._nse_client.fetch_equity_classification(
                    str(row["symbol"]), str(row["isin"])
                )
                changed += self._repository.upsert_classification({
                    "symbol": record.symbol, "isin": record.isin,
                    "macro_sector": record.macro_sector, "sector": record.sector,
                    "industry": record.industry, "basic_industry": record.basic_industry,
                    "source_checksum": record.source_checksum,
                    "source_payload": _thaw(record.source_payload),
                }, effective_from)
                completed += 1
            except NseDataValidationError as error:
                message = str(error).replace("\n", " ")[:500]
                if error.field in {"industryInfo", "macro", "sector", "industry", "basicIndustry"}:
                    missing += 1
                    self._repository.mark_classification_missing(str(row["isin"]), message)
                else:
                    failed += 1
                    self._repository.mark_classification_failed(str(row["isin"]), message)
                    errors.append(f'{row["symbol"]}: {message}')
            except NseRequestError as error:
                message = str(error).replace("\n", " ")[:500]
                if error.status_code == 404:
                    missing += 1
                    self._repository.mark_classification_missing(str(row["isin"]), message)
                else:
                    failed += 1
                    self._repository.mark_classification_failed(str(row["isin"]), message)
                    errors.append(f'{row["symbol"]}: {message}')
            except Exception as error:
                failed += 1
                message = str(error).replace("\n", " ")[:500]
                self._repository.mark_classification_failed(str(row["isin"]), message)
                errors.append(f'{row["symbol"]}: {message}')
        result = {
            "requested": len(rows), "completed": completed, "changed": int(changed),
            "missing": missing, "failed": failed, "errors": errors[:20],
            "sourceMetrics": self._nse_client.metrics,
        }
        if run_id is not None:
            from pattern_engine.enums import ImportStatus
            status = ImportStatus.PARTIAL if completed and failed else ImportStatus.FAILED if failed else ImportStatus.COMPLETED
            self._run_repository.update_import_run(
                run_id, status, securities_completed=completed, securities_failed=failed,
                rows_downloaded=completed, rows_inserted=int(changed),
                rows_rejected=missing + failed,
                error_summary="; ".join(errors[:20]) or None,
                source_metrics=self._nse_client.metrics,
            )
            result["runId"] = run_id
            result["status"] = status.value
        return result


def _thaw(value):
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
