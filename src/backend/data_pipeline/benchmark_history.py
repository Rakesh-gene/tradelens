"""Idempotent NSE broad-market benchmark ingestion."""

from __future__ import annotations

from datetime import date, timedelta

from data_pipeline.nse_api import NseApiClient
from repositories.market_data import MarketDataRepository


class BenchmarkHistoryService:
    """Keep the benchmark required by relative-strength features up to date."""

    DEFAULT_INDEX = "NIFTY 500"
    DEFAULT_INDICES = ("NIFTY 500", "NIFTY 50")

    def __init__(
        self,
        repository: MarketDataRepository,
        nse_client: NseApiClient,
        *,
        index_name: str | None = None,
        index_names: tuple[str, ...] | None = None,
    ) -> None:
        self._repository = repository
        self._nse_client = nse_client
        requested = index_names or ((index_name,) if index_name is not None else self.DEFAULT_INDICES)
        self._index_names = tuple(" ".join(value.strip().upper().split()) for value in requested)
        if not self._index_names or any(not value for value in self._index_names):
            raise ValueError("At least one index name is required")

    def ensure_history(self, from_date: date, to_date: date) -> int:
        """Fill leading and trailing benchmark gaps and return persisted rows."""

        if from_date > to_date:
            raise ValueError("from_date cannot be after to_date")
        written = 0
        for index_name in self._index_names:
            earliest, latest = self._repository.get_index_bar_date_range(index_name)
            ranges: list[tuple[date, date]] = []
            if earliest is None or latest is None:
                ranges.append((from_date, to_date))
            else:
                if from_date < earliest:
                    ranges.append((from_date, earliest - timedelta(days=1)))
                if latest < to_date:
                    ranges.append((latest + timedelta(days=1), to_date))

            records = []
            for range_from, range_to in ranges:
                records.extend(
                    self._nse_client.fetch_index_history(index_name, range_from, range_to)
                )
            bars = [
                {
                    "index_code": index_name,
                    "index_name": record.index_name,
                    "trading_date": record.trading_date,
                    "open_price": record.open_price,
                    "high_price": record.high_price,
                    "low_price": record.low_price,
                    "close_price": record.close_price,
                    "volume": record.volume,
                    "source_name": "NSE",
                    "source_checksum": record.source_checksum,
                }
                for record in records
            ]
            written += self._repository.upsert_index_bars(index_name, bars)
        return written
