from __future__ import annotations

import csv
import io
from datetime import datetime
from time import perf_counter
from typing import Protocol

from data_pipeline.nse_api import NseApiClient


class EquityRepository(Protocol):
    def upsert_equities(self, equities: list[dict[str, object]]) -> int:
        ...


class NseDataCollector:
    """Imports NSE's equity master list into the application database."""

    def __init__(self, repository: EquityRepository, nse_client: NseApiClient | None = None, *, run_repository=None) -> None:
        self._repository = repository
        self._nse_client = nse_client or NseApiClient()
        self._run_repository = run_repository

    def DownloadEquities(self) -> int:
        """Download, validate, and upsert NSE equity master records.

        The PascalCase name is intentionally retained for the scheduled-job API.
        """
        started = perf_counter(); run_id = None
        if self._run_repository is not None:
            from pattern_engine.enums import ImportJobType, ImportStatus
            run_id = self._run_repository.create_import_run(ImportJobType.EQUITY_MASTER, "manual")
            self._run_repository.update_import_run(run_id, ImportStatus.RUNNING)
        try:
            csv_content = self._nse_client.download_equities_csv()
            equities = self._parse_equities(csv_content)
            count = self._repository.upsert_equities(equities)
        except Exception as exc:
            if run_id:
                self._run_repository.update_import_run(run_id, ImportStatus.FAILED, rows_rejected=1, error_summary=str(exc)[:500], duration_ms=round((perf_counter() - started) * 1000), source_metrics=getattr(self._nse_client, "metrics", {}))
            raise
        if run_id:
            self._run_repository.update_import_run(run_id, ImportStatus.COMPLETED, rows_downloaded=len(equities), rows_inserted=count, duration_ms=round((perf_counter() - started) * 1000), source_metrics=getattr(self._nse_client, "metrics", {}))
        return count

    def download_equities(self) -> int:
        """PEP-8 alias for :meth:`DownloadEquities`."""
        return self.DownloadEquities()

    @staticmethod
    def _parse_equities(csv_content: bytes) -> list[dict[str, object]]:
        reader = csv.DictReader(
            io.StringIO(csv_content.decode("utf-8-sig")), skipinitialspace=True
        )
        required_columns = {
            "SYMBOL", "NAME OF COMPANY", "SERIES", "DATE OF LISTING",
            "PAID UP VALUE", "MARKET LOT", "ISIN NUMBER", "FACE VALUE",
        }
        if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
            raise ValueError("The downloaded NSE file does not have the expected equity schema")

        equities: list[dict[str, object]] = []
        for row in reader:
            isin = (row["ISIN NUMBER"] or "").strip()
            symbol = (row["SYMBOL"] or "").strip()
            if not isin or not symbol:
                continue
            try:
                listed_on = datetime.strptime(row["DATE OF LISTING"].strip(), "%d-%b-%Y").date()
                equities.append(
                    {
                        "symbol": symbol,
                        "company_name": (row["NAME OF COMPANY"] or "").strip(),
                        "series": (row["SERIES"] or "").strip(),
                        "listed_on": listed_on,
                        "paid_up_value": (row["PAID UP VALUE"] or "").strip(),
                        "market_lot": int((row["MARKET LOT"] or "").strip()),
                        "isin": isin,
                        "face_value": (row["FACE VALUE"] or "").strip(),
                    }
                )
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid NSE equity row for symbol {symbol!r}") from error
        return equities
