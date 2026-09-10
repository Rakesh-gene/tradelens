"""Idempotent NSE broad-market benchmark ingestion."""

from __future__ import annotations

from datetime import date, timedelta

from data_pipeline.nse_api import NseApiClient
from repositories.market_data import MarketDataRepository


class BenchmarkHistoryService:
    """Keep the benchmark required by relative-strength features up to date."""

    DEFAULT_INDEX = "NIFTY 500"

    def __init__(
        self,
        repository: MarketDataRepository,
        nse_client: NseApiClient,
        *,
        index_name: str = DEFAULT_INDEX,
    ) -> None:
        self._repository = repository
        self._nse_client = nse_client
        self._index_name = " ".join(index_name.strip().upper().split())
        if not self._index_name:
            raise ValueError("index_name is required")

    def ensure_history(self, from_date: date, to_date: date) -> int:
        """Fill leading and trailing benchmark gaps and return persisted rows."""

        if from_date > to_date:
            raise ValueError("from_date cannot be after to_date")
        earliest, latest = self._repository.get_index_bar_date_range(self._index_name)
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
                self._nse_client.fetch_index_history(
                    self._index_name, range_from, range_to
                )
            )
        bars = [
            {
                "index_code": self._index_name,
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
        return self._repository.upsert_index_bars(self._index_name, bars)
