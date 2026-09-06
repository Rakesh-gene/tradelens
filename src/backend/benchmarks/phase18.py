"""Bounded-memory Phase 18 volume benchmark for the history ingestion boundary."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from decimal import Decimal
import json
from time import perf_counter
from typing import Sequence

from data_pipeline.models import NseEquityHistoryRecord, freeze_json_value
from data_pipeline.normalization import raw_bar_record


def run_backfill_volume_benchmark(rows: int, batch_size: int) -> dict[str, object]:
    """Normalize a production-scale row count without retaining all rows in memory."""

    if rows <= 0 or batch_size <= 0:
        raise ValueError("rows and batch_size must be positive")
    started = perf_counter()
    processed = batches = checksum_bytes = 0
    session_start = date(2016, 1, 1)
    while processed < rows:
        current_size = min(batch_size, rows - processed)
        batch = []
        for offset in range(current_size):
            absolute = processed + offset
            symbol_index, session_index = divmod(absolute, 3650)
            symbol = f"BENCH{symbol_index:04d}"
            isin = f"INBENCH{symbol_index:08d}"[-12:]
            trading_date = session_start + timedelta(days=session_index)
            record = NseEquityHistoryRecord(
                symbol=symbol, source_isin=isin, series="EQ", trading_date=trading_date,
                open_price=Decimal("100"), high_price=Decimal("102"),
                low_price=Decimal("99"), close_price=Decimal("101"), volume=1_000_000,
                deliverable_quantity=500_000, delivery_percentage=Decimal("50"),
                source_checksum=f"benchmark-{absolute}",
                source_payload=freeze_json_value({"row": absolute}),
            )
            batch.append(raw_bar_record(record, isin, "phase18-benchmark"))
        checksum_bytes += sum(len(str(row["source_checksum"])) for row in batch)
        processed += len(batch)
        batches += 1
    duration = perf_counter() - started
    return {
        "rows": processed,
        "batchSize": batch_size,
        "batches": batches,
        "durationSeconds": round(duration, 3),
        "rowsPerSecond": round(processed / duration, 2) if duration else None,
        "checksumBytes": checksum_bytes,
        "memoryPolicy": "only one batch retained",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.phase18")
    parser.add_argument("--rows", type=int, default=6_000_000)
    parser.add_argument("--batch-size", type=int, default=10_000)
    arguments = parser.parse_args(argv)
    print(json.dumps(run_backfill_volume_benchmark(arguments.rows, arguments.batch_size), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
