"""Command-line entry points for scheduler-agnostic market-data imports."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from typing import Sequence

from data_pipeline.history_backfill import BackfillRequest, HistoryBackfillService
from data_pipeline.daily_delta import DailyDeltaRequest, DailyDeltaService
from data_pipeline.nse_api import NseApiClient
from data_pipeline.nse_data_collector import NseDataCollector
from data_pipeline.nse_classification_collector import NseClassificationCollector
from pattern_engine.enums import ImportStatus
from repositories.equities import PostgresEquityRepository
from repositories.market_data import PostgresMarketDataRepository
from repositories.operations import PostgresOperationsRepository
from operations.monitoring import StructuredEventLogger
from server import load_local_environment


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data_pipeline.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backfill = subparsers.add_parser("backfill-history", help="Import historical NSE equity data")
    backfill.add_argument("--from-date", type=_parse_date)
    backfill.add_argument("--to-date", type=_parse_date)
    backfill.add_argument("--years", type=int, default=10)
    backfill.add_argument("--symbol")
    backfill.add_argument("--isin")
    backfill.add_argument("--batch-size", type=int, default=100)
    backfill.add_argument("--max-securities", type=int)
    backfill.add_argument("--resume", action="store_true")
    backfill.add_argument("--retry-failed", action="store_true")
    backfill.add_argument("--force", action="store_true", help="Re-download checkpointed history ranges")
    backfill.add_argument("--dry-run", action="store_true")
    daily = subparsers.add_parser("sync-daily", help="Import the latest completed NSE session")
    daily.add_argument("--as-of", type=_parse_date)
    daily.add_argument("--repair-sessions", type=int, default=10)
    daily.add_argument("--symbol")
    daily.add_argument("--isin")
    daily.add_argument("--max-securities", type=int)
    daily.add_argument("--dry-run", action="store_true")
    classifications = subparsers.add_parser(
        "sync-classifications", help="Import NSE equity sector and industry classifications"
    )
    classifications.add_argument("--symbol", action="append", default=[])
    classifications.add_argument("--limit", type=int, default=50)
    classifications.add_argument("--all", action="store_true", dest="all_equities")
    contract = subparsers.add_parser(
        "verify-nse-contract", help="Run an opt-in live NSE parser contract check"
    )
    contract.add_argument("--symbol", default="RELIANCE")
    contract.add_argument("--from-date", type=_parse_date, default=date(2024, 1, 1))
    contract.add_argument("--to-date", type=_parse_date, default=date(2024, 1, 5))
    contract.add_argument("--actions-from", type=_parse_date, default=date(2024, 7, 1))
    contract.add_argument("--actions-to", type=_parse_date, default=date(2024, 11, 30))
    arguments = parser.parse_args(argv)

    if arguments.command == "backfill-history":
        return _backfill_history(arguments)
    if arguments.command == "sync-daily":
        return _sync_daily(arguments)
    if arguments.command == "sync-classifications":
        return _sync_classifications(arguments)
    if arguments.command == "verify-nse-contract":
        return _verify_nse_contract(arguments)
    parser.error("Unsupported command")
    return 2


def _backfill_history(arguments: argparse.Namespace) -> int:
    today = date.today()
    to_date = arguments.to_date or today
    from_date = arguments.from_date or _years_before(to_date, arguments.years)
    if arguments.years <= 0:
        raise SystemExit("--years must be positive")
    request = BackfillRequest(
        from_date=from_date,
        to_date=to_date,
        symbol=arguments.symbol,
        isin=arguments.isin,
        batch_size=arguments.batch_size,
        max_securities=arguments.max_securities,
        resume=arguments.resume,
        retry_failed=arguments.retry_failed,
        force=arguments.force,
        dry_run=arguments.dry_run,
        initiated_by="recovery" if arguments.resume or arguments.retry_failed else "manual",
    )
    load_local_environment()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required for market-data imports")

    repository = PostgresMarketDataRepository(dsn, apply_migrations=not request.dry_run)
    event_logger = StructuredEventLogger(PostgresOperationsRepository(dsn, apply_migrations=False)) if not request.dry_run else None
    client = NseApiClient()
    if not request.dry_run:
        NseDataCollector(PostgresEquityRepository(dsn), client, run_repository=repository).download_equities()
    result = HistoryBackfillService(repository, client, event_logger=event_logger).run(request)
    print(json.dumps({
        "runId": result.run_id,
        "status": result.status.value if result.status else "DRY_RUN",
        "securities": [
            {
                "isin": item.isin,
                "symbol": item.symbol,
                "fromDate": item.requested_from_date.isoformat(),
                "toDate": item.requested_to_date.isoformat(),
                "chunks": [[start.isoformat(), end.isoformat()] for start, end in item.chunks],
                "rowsDownloaded": item.rows_downloaded,
                "rowsInserted": item.rows_inserted,
                "actionsInserted": item.actions_inserted,
                "warnings": item.warnings,
                "error": item.error,
            }
            for item in result.securities
        ],
    }, indent=2))
    return 0 if result.status in {None, ImportStatus.COMPLETED} else 1


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Dates must use YYYY-MM-DD") from error


def _sync_daily(arguments: argparse.Namespace) -> int:
    load_local_environment()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required for market-data imports")
    as_of = arguments.as_of or date.today()
    request = DailyDeltaRequest(
        as_of=as_of, repair_sessions=arguments.repair_sessions,
        symbol=arguments.symbol, isin=arguments.isin,
        max_securities=arguments.max_securities, dry_run=arguments.dry_run,
    )
    repository = PostgresMarketDataRepository(dsn, apply_migrations=not request.dry_run)
    event_logger = StructuredEventLogger(PostgresOperationsRepository(dsn, apply_migrations=False)) if not request.dry_run else None
    client = NseApiClient()
    if not request.dry_run:
        NseDataCollector(PostgresEquityRepository(dsn), client, run_repository=repository).download_equities()
    result = DailyDeltaService(repository, client, event_logger=event_logger).run(request)
    print(json.dumps({
        "runId": result.run_id,
        "status": result.status.value if result.status else "DRY_RUN",
        "latestSession": result.latest_session.isoformat() if result.latest_session else None,
        "securities": [
            {"isin": item.isin, "symbol": item.symbol, "fromDate": item.from_date.isoformat(),
             "toDate": item.to_date.isoformat(), "rowsDownloaded": item.rows_downloaded,
             "rowsInserted": item.rows_inserted, "rowsUpdated": item.rows_updated,
             "actionsInserted": item.actions_inserted,
             "changedFromDate": item.changed_from_date.isoformat() if item.changed_from_date else None,
             "error": item.error, "warnings": item.warnings}
            for item in result.securities
        ],
    }, indent=2))
    return 0 if result.status in {None, ImportStatus.COMPLETED} else 1


def _years_before(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:  # 29 February
        return value.replace(year=value.year - years, month=2, day=28)


def _sync_classifications(arguments: argparse.Namespace) -> int:
    load_local_environment()
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required for classification imports")
    if arguments.limit <= 0:
        raise SystemExit("--limit must be positive")
    market = PostgresMarketDataRepository(dsn)
    collector = NseClassificationCollector(
        PostgresEquityRepository(dsn, apply_migrations=False), NseApiClient(),
        run_repository=market,
    )
    if arguments.symbol:
        result = collector.refresh_symbols(arguments.symbol)
    elif arguments.all_equities:
        result = collector.backfill_all()
    else:
        result = collector.refresh_new_and_stale(limit=arguments.limit, initiated_by="manual")
    print(json.dumps(result, indent=2))
    return 0 if not result["failed"] else 1


def _verify_nse_contract(arguments: argparse.Namespace) -> int:
    """Exercise the real NSE boundary without mutating application storage."""

    client = NseApiClient()
    history = client.fetch_equity_history(
        arguments.symbol, arguments.from_date, arguments.to_date
    )
    actions = client.fetch_corporate_actions(
        arguments.symbol, arguments.actions_from, arguments.actions_to
    )
    payload = {
        "symbol": arguments.symbol.strip().upper(),
        "history": {
            "rows": len(history),
            "firstDate": history[0].trading_date.isoformat() if history else None,
            "lastDate": history[-1].trading_date.isoformat() if history else None,
        },
        "corporateActions": [
            {
                "type": action.action_type,
                "exDate": action.ex_date.isoformat(),
                "description": action.raw_description,
            }
            for action in actions
        ],
        "sourceMetrics": client.metrics,
    }
    print(json.dumps(payload, indent=2))
    return 0 if history else 1


if __name__ == "__main__":
    raise SystemExit(main())
