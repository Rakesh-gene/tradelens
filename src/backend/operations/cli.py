"""Scheduler-neutral operational commands for TradeLens."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from typing import Sequence

from operations.monitoring import OperationalMonitor, StructuredEventLogger
from operations.recovery import RecoveryService
from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.models import serialize_value
from pattern_engine.research import BacktestService, PatternReplayEvaluator
from pattern_engine.runner import PatternEngineRunner, PatternEngineVersions
from repositories.market_data import PostgresMarketDataRepository
from repositories.operations import PostgresOperationsRepository
from repositories.patterns import PostgresPatternRepository
from repositories.research import PostgresResearchRepository
from server import load_local_environment


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m operations.cli",
        epilog="History recovery remains available through: python -m data_pipeline.cli backfill-history --resume|--retry-failed",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show import, source, anomaly, and calculation-lag status")
    coverage = commands.add_parser("validate-coverage", help="Find and optionally persist missing-session anomalies")
    coverage.add_argument("--from-date", type=_date); coverage.add_argument("--to-date", type=_date)
    coverage.add_argument("--limit", type=int, default=5000); coverage.add_argument("--no-persist", action="store_true")
    lineage = commands.add_parser("lineage", help="Trace a pattern to adjusted bars, actions, features, and versions")
    lineage.add_argument("--pattern-id", required=True)
    plan = commands.add_parser("import-plan", help="Print a read-only ten-year history import plan")
    plan.add_argument("--from-date", type=_date); plan.add_argument("--to-date", type=_date)
    plan.add_argument("--years", type=int, default=10); plan.add_argument("--isin"); plan.add_argument("--symbol"); plan.add_argument("--max-securities", type=int)
    rebuild = commands.add_parser("rebuild-security", help="Rebuild adjustments, features, swings, zones, and patterns")
    _target_arguments(rebuild, require_range=True); rebuild.add_argument("--dry-run", action="store_true")
    explain = commands.add_parser("explain-detector", help="Run one point-in-time detector scan with explanation output")
    _target_arguments(explain); explain.add_argument("--pattern-type")
    benchmark = commands.add_parser("benchmark-scan", help="Benchmark production detectors over a bounded universe")
    _version_arguments(benchmark); benchmark.add_argument("--as-of", type=_date, default=date.today()); benchmark.add_argument("--max-securities", type=int, default=100)
    backtest = commands.add_parser("run-backtest", help="Run a reproducible point-in-time backtest")
    _version_arguments(backtest); backtest.add_argument("--from-date", type=_date, required=True); backtest.add_argument("--to-date", type=_date, required=True)
    backtest.add_argument("--index-code", required=True); backtest.add_argument("--filters-json", default="{}"); backtest.add_argument("--minimum-sample-size", type=int, default=30)
    resume = commands.add_parser("resume-backtest", help="Resume the unprocessed suffix of a failed backtest as a linked run")
    resume.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    dependencies = _dependencies()
    try:
        if args.command == "status": result = dependencies["monitor"].status()
        elif args.command == "lineage": result = dependencies["monitor"].lineage(args.pattern_id)
        elif args.command == "validate-coverage": result = dependencies["monitor"].validate_coverage(args.from_date, args.to_date, limit=args.limit, persist=not args.no_persist)
        elif args.command == "import-plan": result = _import_plan(args, dependencies["market"])
        elif args.command == "rebuild-security": result = dependencies["recovery"].rebuild_security(args.isin, args.from_date, args.to_date, _versions(args), dry_run=args.dry_run)
        elif args.command == "explain-detector": result = dependencies["recovery"].explain(_security(dependencies["market"], args.isin), args.as_of, _versions(args), pattern_type=args.pattern_type)
        elif args.command == "benchmark-scan": result = dependencies["recovery"].benchmark(dependencies["market"].list_eligible_securities(), args.as_of, _versions(args), maximum=args.max_securities)
        elif args.command == "run-backtest": result = dependencies["backtest"].start({"fromDate": args.from_date, "toDate": args.to_date, "universe": {"indexCode": args.index_code}, "filters": _json_object(args.filters_json), "minimumSampleSize": args.minimum_sample_size, "versions": {"engine": args.engine_version, "configuration": dependencies["configuration"].version, "feature": args.feature_version, "adjustment": args.adjustment_version}}, requested_by=None)
        elif args.command == "resume-backtest": result = dependencies["backtest"].resume(args.run_id)
        else: parser.error("Unsupported command")
    except Exception as exc:
        dependencies["logger"].emit("operator_command_failed", level="ERROR", job_type=args.command, error_class=type(exc).__name__, details={"message": str(exc)})
        raise SystemExit(str(exc)) from exc
    print(json.dumps(serialize_value(result), indent=2, sort_keys=True))
    return 0


def _dependencies():
    load_local_environment(); dsn = os.getenv("DATABASE_URL")
    if not dsn: raise SystemExit("DATABASE_URL is required")
    configuration = load_pattern_engine_configuration()
    market = PostgresMarketDataRepository(dsn)
    patterns = PostgresPatternRepository(dsn, apply_migrations=False)
    operations = PostgresOperationsRepository(dsn, apply_migrations=False)
    research = PostgresResearchRepository(dsn, apply_migrations=False)
    runner = PatternEngineRunner(market, patterns, market, configuration)
    logger = StructuredEventLogger(operations)
    return {"configuration": configuration, "market": market, "monitor": OperationalMonitor(operations, daily_processing_window_minutes=configuration.section("operations")["daily_processing_window_minutes"]), "logger": logger, "recovery": RecoveryService(market, runner, configuration, logger=logger), "backtest": BacktestService(research, PatternReplayEvaluator(runner), configuration_version=configuration.version)}


def _import_plan(args, repository):
    from data_pipeline.history_backfill import BackfillRequest, HistoryBackfillService
    end = args.to_date or date.today(); start = args.from_date or _years_before(end, args.years)
    request = BackfillRequest(start, end, symbol=args.symbol, isin=args.isin, max_securities=args.max_securities, dry_run=True)
    return {"fromDate": start, "toDate": end, "securities": [serialize_value(item) for item in HistoryBackfillService(repository).plan(request)]}


def _target_arguments(parser, require_range=False):
    parser.add_argument("--isin", required=True); parser.add_argument("--as-of", type=_date, default=date.today())
    if require_range: parser.add_argument("--from-date", type=_date, required=True); parser.add_argument("--to-date", type=_date, required=True)
    _version_arguments(parser)
def _version_arguments(parser):
    parser.add_argument("--engine-version", default="v1"); parser.add_argument("--feature-version", default="v1"); parser.add_argument("--adjustment-version", default="v1")
def _versions(args): return PatternEngineVersions(args.engine_version, args.feature_version, args.adjustment_version)
def _security(repository, isin):
    result = next((row for row in repository.list_eligible_securities() if row["isin"] == isin), None)
    if result is None: raise ValueError(f"Unknown ISIN: {isin}")
    return result
def _json_object(value):
    try: result = json.loads(value)
    except json.JSONDecodeError as exc: raise ValueError("--filters-json must contain valid JSON") from exc
    if not isinstance(result, dict): raise ValueError("--filters-json must contain a JSON object")
    return result
def _date(value):
    try: return date.fromisoformat(value)
    except ValueError as exc: raise argparse.ArgumentTypeError("Dates must use YYYY-MM-DD") from exc
def _years_before(value, years):
    if years <= 0: raise ValueError("--years must be positive")
    try: return value.replace(year=value.year - years)
    except ValueError: return value.replace(year=value.year - years, day=28)


if __name__ == "__main__": raise SystemExit(main())
