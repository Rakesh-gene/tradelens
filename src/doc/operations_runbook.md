# TradeLens operations runbook

Run commands from `src/backend`. Local configuration is loaded from `.env` and
must provide `DATABASE_URL`; never place its value in command output or logs.

## Health and data quality

```powershell
py -3.11 -m operations.cli status
py -3.11 -m operations.cli validate-coverage --from-date 2026-01-01 --to-date 2026-09-05
```

`status` reports the last terminal import/scan run by job type, checkpoint
success and failure counts, NSE request counters, row counts, open anomalies,
and adjustment/feature/pattern lag. Coverage validation compares each eligible
security with the observed exchange-session calendar and records unresolved
missing-session anomalies. Use `--no-persist` for a read-only check.

## Import and recovery

```powershell
py -3.11 -m operations.cli import-plan --years 10 --max-securities 20
py -3.11 -m data_pipeline.cli backfill-history --years 10 --dry-run
py -3.11 -m data_pipeline.cli backfill-history --years 10 --resume
py -3.11 -m data_pipeline.cli backfill-history --years 10 --retry-failed
py -3.11 -m data_pipeline.cli sync-daily --as-of 2026-09-05
```

Dry runs perform no writes. Resume closes abandoned running imports and
continues from committed checkpoints. Retry-failed selects failed security
checkpoints without reprocessing successful securities.

Admin full-pipeline runs use three concurrent equity workers by default. Set
`ADMIN_PIPELINE_WORKERS` to a value from 1 through 8 before starting the backend
to tune database/CPU overlap. NSE request starts remain globally limited to two
per second, while bounded in-flight requests prevent one slow response from
blocking unrelated equities. Corporate-action date windows are fetched once
and reused across the universe. Do not raise the NSE history window above 100
days: the live endpoint can silently return only the trailing portion of a
larger requested range.

## Dependency-ordered rebuild and explanations

```powershell
py -3.11 -m operations.cli rebuild-security --isin INE000000001 --from-date 2020-01-01 --to-date 2026-09-05 --engine-version v1 --feature-version v1 --adjustment-version v1
py -3.11 -m operations.cli explain-detector --isin INE000000001 --as-of 2026-09-05 --pattern-type BASE-VCP
py -3.11 -m operations.cli lineage --pattern-id <pattern-uuid>
```

The rebuild order is adjustments, features, swings/zones, then the production
pattern runner. `--dry-run` prints the intended range and versions. Explanation
mode is point-in-time and does not write pattern instances or events.

## Backtests and performance

```powershell
py -3.11 -m operations.cli run-backtest --from-date 2018-01-01 --to-date 2026-09-05 --index-code NIFTY500 --filters-json '{"patternType":"BASE-VCP","minRs6m":90,"stage2":true}'
py -3.11 -m operations.cli resume-backtest --run-id <failed-run-uuid>
py -3.11 -m operations.cli benchmark-scan --as-of 2026-09-05 --max-securities 100
```

Resume creates a linked run beginning after the last completely processed
session. Benchmark output includes duration, throughput, completed/failed
securities, and candidate count. Increase the sample only after a bounded run
is healthy; add numeric dependencies only after measured evidence and parity
tests.

## Failure response

1. Run `status` and note the run ID, job type, requested range, error class, and
   failed-security count.
2. Run coverage validation without persistence if source completeness is
   uncertain.
3. Use checkpoint resume or failed-only retry for imports.
4. Use `rebuild-security` when corrections or corporate actions invalidate
   downstream calculations.
5. Re-run a bounded detector explanation before returning the security to the
   universe job.
