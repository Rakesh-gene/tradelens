# Positional Trading Pattern Engine — Low-Level Implementation Plan

- **Plan version:** 1.0
- **Sector rotation extension:** `sector-rotation-v1` reads same-session feature
  medians through `repositories/sector_rotation.py`; no migration or external
  feed is required. `pattern_engine/sector_rotation.py` owns zone classification
  and the explicit short/medium-horizon momentum proxy from specification 131.
  Queries aggregate sectors and paginate strength-ranked constituents in SQL.
  Retain effective-dated membership, nulls and coverage; never backdate sectors.
- **Source specification:** `src/doc/positional_trading_pattern_engine_spec.md`
- **Target application:** TradeLens
- **Execution model:** Indian equities, end-of-day processing
- **Primary source:** NSE historical data and corporate actions

Client screens, browser behavior, and concrete API wire contracts are specified
separately in
`src/doc/positional_trading_pattern_engine_client_implementation_plan.md`.

## 1. Purpose of this plan

This document translates the canonical pattern-engine specification into an
ordered engineering plan for the existing TradeLens repository. It defines the
files, classes, database tables, interfaces, algorithms, tests, operational
behavior, and completion gates required for each phase.

The plan covers the complete specification:

- NSE security master, historical OHLCV, corporate actions, benchmark, sector,
  and optional delivery data;
- corporate-action-adjusted, point-in-time-safe daily bars;
- common technical features;
- confirmed swings and support/resistance zones;
- all primary, supporting, and failure patterns;
- quality, maturity, context, and setup scoring;
- pattern lifecycle, deduplication, expiration, and event history;
- protected APIs and the user-facing technical fingerprint;
- backtesting, outcome measurement, threshold calibration, observability, and
  operational recovery.

## 2. Existing baseline

The following pieces already exist and must be extended rather than replaced:

- `data_pipeline/NseDataCollector` imports the NSE equity master.
- `data_pipeline/NseApiClient` owns NSE HTTP headers, cookies, and downloads.
- `nse_equities` uses ISIN as its stable identifier and stores the current NSE
  symbol and listing metadata.
- PostgreSQL migrations are append-only and run through `MigrationRunner`.
- Repository contracts are represented by Python protocols and PostgreSQL
  implementations.
- The backend uses `ThreadingHTTPServer` and thin HTTP handlers.
- JWT authentication protects application APIs.
- The React application has protected-route behavior and an overview page.

The next migration number is `006`. Existing migrations must not be edited.

## 3. Target execution flow

```text
NSE security master
        |
        +--> NSE historical OHLCV --------+
        |                                  |
        +--> NSE corporate actions --------+--> normalized source bars
        |                                  |          |
        +--> benchmark/sector OHLCV --------+          v
        |                                      adjusted analysis bars
        +--> optional delivery data                    |
                                                       v
                                                feature snapshots
                                                       |
                                                       v
                                            confirmed swing points
                                                       |
                                                       v
                                           support/resistance zones
                                                       |
                         +-----------------------------+------------------+
                         |                                                |
                         v                                                v
                 supporting detectors                            primary detectors
                         |                                                |
                         +----------------------+-------------------------+
                                                |
                                                v
                                  quality / maturity / context scores
                                                |
                                                v
                                      pattern lifecycle service
                                                |
                                +---------------+---------------+
                                |                               |
                                v                               v
                       current instances                 immutable events
                                |                               |
                                +---------------+---------------+
                                                |
                                      +---------+---------+
                                      |                   |
                                      v                   v
                                  product API          backtesting
```

## 4. Repository layout to add

```text
src/backend/
  configuration/
    pattern_engine.toml
  data_pipeline/
    models.py
    import_state.py
    nse_api.py
    nse_data_collector.py
    nse_history_collector.py
    nse_corporate_action_collector.py
    adjustment_service.py
    backfill_job.py
    delta_job.py
    cli.py
  pattern_engine/
    __init__.py
    models.py
    enums.py
    configuration.py
    features.py
    relative_strength.py
    swings.py
    zones.py
    scoring.py
    context.py
    lifecycle.py
    runner.py
    detectors/
      base.py
      base_vcp.py
      base_flat.py
      base_52wh.py
      breakout.py
      pullback_breakout_retest.py
      pullback_ema20.py
      pullback_sma50.py
      supporting.py
      failure.py
  backtesting/
    models.py
    replay.py
    outcomes.py
    repository.py
  repositories/
    market_data.py
    patterns.py
    backtests.py
  server_http/
    api.py
    pattern_api.py
```

Tests should mirror these boundaries with deterministic fixtures under
`src/backend/tests/fixtures/` and focused `test_*.py` modules.

## 5. Shared implementation rules

1. All dates in the engine represent NSE trading dates, not UTC timestamps.
2. All timestamps representing imports or state transitions use `TIMESTAMPTZ`.
3. Database price columns use `NUMERIC`; engine calculations use one consistent
   numeric representation and explicitly round only at persistence/display
   boundaries.
4. Detectors never query or write PostgreSQL. They accept typed inputs and
   return `PatternCandidate` objects.
5. Thresholds and scoring weights are loaded from versioned configuration.
6. A calculation never consumes bars, actions, constituents, or pivots that
   were not available as of the calculation date.
7. Every persisted pattern records the engine version, configuration version,
   input end date, and adjustment-data version.
8. Jobs are idempotent, resumable, rate-limited, and safe to run twice.
9. Source payloads are validated before persistence. HTML block pages, partial
   CSVs, and structurally invalid JSON are import failures.
10. Setup score is a ranking score and must never be labeled as probability of
    profit.

---

# Phase 0 — Canonical contracts and configuration

**Status:** Complete — reviewed and verified on 2026-09-04.

## Objective

Create stable domain types and make every heuristic configurable before any
calculation code is added.

## Files and types

### `pattern_engine/enums.py`

Define string enums for:

- `PatternClass`: `TREND`, `BASE`, `BREAKOUT`, `PULLBACK`, `COMPRESSION`,
  `MOMENTUM`, `FAILURE`.
- `PatternState`: `DETECTED`, `FORMING`, `MATURE`, `READY`, `TRIGGERED`,
  `CONFIRMED`, `FAILED`, `INVALIDATED`, `EXPIRED`.
- `PatternEventType`: detected, state changed, pivot updated, quality changed,
  maturity changed, triggered, confirmed, failed, invalidated, expired.
- `SwingType`: high and low.
- `ZoneType`: resistance and support.
- `ImportJobType`: equity master, history backfill, corporate-action backfill,
  daily delta, adjustment rebuild, feature rebuild, pattern scan.
- `ImportStatus`: pending, running, completed, partial, failed, cancelled.

### `pattern_engine/models.py`

Add immutable/slotted dataclasses:

- `DailyBar`: ISIN, symbol, trading date, open, high, low, close, volume,
  optional delivery quantity/percentage, and data version.
- `CorporateAction`: stable source key, ISIN, action type, ex-date, record date,
  ratio/value, source announcement date, raw source attributes.
- `TechnicalFeatureSnapshot`: one date plus all common feature values.
- `SwingPoint`: pivot date, confirmation date, type, price, NATR, move size,
  meaningful flag.
- `PriceZone`: type, start/end date, median price, tolerance, dispersion,
  source swing IDs, test count.
- `DetectionContext`: as-of date, benchmark/sector snapshots, available
  supporting signals, and configuration version.
- `PatternCandidate`: classification, type, variant, window, state, scores,
  prices, typed measurements, supporting identifiers, invalidation rule.
- `PatternInstance`: persisted identity and lifecycle fields.

### `configuration/pattern_engine.toml`

Use TOML because Python 3.11 includes `tomllib`; no YAML dependency is needed.
Sections must include:

- `engine`, `data`, `swings`, `zones`, `liquidity`;
- `vcp`, `flat_base`, `base_52wh`;
- `breakout`, `breakout_retest`, `ema20_pullback`, `sma50_pullback`;
- `trend`, `compression`, `momentum`, `volume`, `failure`;
- `quality_weights`, `maturity_weights`, `context_weights`, `setup_weights`.

`configuration.py` must validate:

- minimums do not exceed maximums;
- weights for a score sum to 100;
- percentage/tolerance values are in valid bounds;
- lookbacks are positive integers;
- the configuration contains a non-empty version.

## Tests

- Every enum serializes to the exact identifier in the specification.
- Default configuration loads successfully.
- Invalid ranges or score weights fail at startup with a clear message.
- Candidate serialization preserves lists, optional values, and measurements.

## Exit criteria

- Every threshold in the specification has a configuration home.
- Later phases can compile against stable domain contracts.

## Completion record

- [x] Canonical string enums cover pattern classes, lifecycle/events, swings,
  zones, import jobs, and import statuses.
- [x] Frozen/slotted domain dataclasses cover bars, actions, features, swings,
  zones, detection context, candidates, and persisted instances.
- [x] Nested source attributes, context, and measurements are immutable and
  serialize to JSON-compatible values without losing lists or optional fields.
- [x] The versioned TOML configuration contains every required section and
  loads without an additional dependency on Python 3.11.
- [x] Startup validation rejects missing sections, empty versions, invalid
  minimum/maximum ranges, invalid percentage bounds, non-positive lookbacks,
  and score weights that do not sum to 100.
- [x] Focused Phase 0 tests and the complete backend test suite pass.

---

# Phase 1 — Import and market-data schema

**Status:** Complete — reviewed and verified on 2026-09-04.

## Objective

Create auditable storage for source data, adjustments, import progress, and
incremental processing.

## Migrations

### `006_create_market_import_tables.sql`

Create `market_import_runs`:

- UUID primary key;
- job type, requested from/to date, configuration JSON;
- status, started/finished timestamps;
- securities total/completed/failed;
- rows downloaded/inserted/updated/rejected;
- error summary and initiating source (`manual`, `scheduler`, `recovery`).

Create `security_import_checkpoints`:

- `(job_type, isin)` primary key;
- earliest/latest successfully imported trading date;
- last attempted range;
- status, retry count, last error;
- last successful run ID and update timestamp.

### `007_create_market_data_tables.sql`

Create `nse_daily_bars_raw`:

- `(isin, trading_date)` primary key;
- open, high, low, close as positive `NUMERIC` values;
- volume and optional deliverable quantity as non-negative `BIGINT`;
- optional delivery percentage;
- NSE series, source name, source checksum;
- source published/imported timestamps;
- raw revision number.

Create `nse_corporate_actions`:

- source event key primary key;
- ISIN and symbol as supplied by NSE;
- action type, ex-date, record date, announcement date;
- numerator, denominator, cash value, currency;
- raw description and `JSONB` payload;
- imported/updated timestamps and source checksum.

Create `adjusted_daily_bars`:

- `(isin, trading_date, adjustment_version)` uniqueness;
- adjusted OHLCV;
- cumulative price and volume adjustment factors;
- adjustment source (`NSE_SOURCE` or `TRADELENS_REBUILT`);
- source revision and action-set checksum;
- generated timestamp.

Add indexes by trading date, ISIN/date descending, action ex-date, and import
status. Add foreign keys to `nse_equities(isin)`.

### `008_create_benchmark_sector_tables.sql`

Create:

- `market_indices`;
- `index_daily_bars`;
- `security_sector_memberships` with effective-from/effective-to dates;
- optional `index_constituent_memberships` with effective dates.

The effective-date columns are required for point-in-time backtesting.

## Repository interfaces

`MarketDataRepository` must provide bounded methods:

- list eligible securities;
- get earliest/latest bar date;
- upsert raw bars/actions;
- load bars for one security/date range;
- replace/upsert adjusted bars for one security/version;
- manage import runs and per-security checkpoints;
- return affected securities/dates after an import.

Avoid one database transaction for the whole equity universe. Commit one
security/date chunk at a time so a failure is resumable.

## Exit criteria

- Migrations apply on an empty and already-migrated database.
- Duplicate bars/actions update safely without creating extra rows.
- Import runs and checkpoints can represent partial completion.

## Completion record

- [x] Migrations `006`–`008` create import runs/checkpoints, raw daily bars,
  corporate actions, versioned adjusted bars, indices, sectors, and
  effective-dated memberships with required constraints and indexes.
- [x] `PostgresMarketDataRepository` applies migrations during construction and
  exposes bounded reads, idempotent upserts, run/checkpoint management, and
  affected-security/date discovery.
- [x] Raw bars use `(isin, trading_date)`, corporate actions use the stable
  source event key, and adjusted bars use
  `(isin, trading_date, adjustment_version)` for conflict-safe persistence.
- [x] Each persistence operation owns a bounded transaction, allowing future
  import jobs to commit per security/date chunk instead of one universe-wide
  transaction.
- [x] Immutable Phase 0 configuration and source payload mappings persist as
  JSON objects rather than string representations.
- [x] Migrations `006`–`008` are applied and recorded in the configured local
  PostgreSQL database; a subsequent repository construction verifies the
  already-migrated path.
- [x] Focused Phase 1 tests and the complete backend test suite pass.

---

# Phase 2 — Hardened NSE client and source normalization

**Status:** Complete — reviewed and verified on 2026-09-04.

## Objective

Extend `NseApiClient` with historical, corporate-action, benchmark, and optional
delivery-data capabilities while keeping NSE behavior outside collectors.

## Client changes

Add methods:

- `fetch_equity_history(symbol, from_date, to_date)`;
- `fetch_corporate_actions(symbol, from_date, to_date)`;
- `fetch_index_history(index_name, from_date, to_date)`;
- `download_eod_report(trading_date)` where NSE provides a bulk daily report;
- `download_delivery_report(trading_date)` when delivery data is enabled.

Centralize:

- browser headers and referer;
- cookie jar and priming;
- timeout and retry policy;
- maximum requests per second;
- bounded exponential backoff with jitter;
- `429`, `403`, timeout, connection-reset, and server-error classification;
- response content-type/body validation;
- date formatting and URL construction.

Follow the referenced NSE repository's behavior: persist/reuse cookies where
appropriate, prime through the NSE homepage, validate file responses, and
split large historical ranges into bounded requests. Do not copy its
TypeScript package into the Python service.

## Normalization

`data_pipeline/models.py` should define source-response DTOs. Parser functions
must:

- trim NSE field names and symbols;
- parse dates using explicit formats;
- normalize series identifiers;
- reject non-positive OHLC values and `high < low`;
- reject bars where open/close fall materially outside high/low;
- handle commas/nulls in volume fields;
- retain the original source payload/checksum for action records;
- return validation errors with symbol, date, and field.

## Tests

Use saved fixtures for:

- valid equity history;
- empty/no-data response;
- corporate actions of every supported type;
- HTML block page returned with HTTP 200;
- rate limiting and transient retry;
- malformed prices, dates, and volume;
- symbol changes where ISIN remains stable.

## Exit criteria

- Fetching one security/date range returns validated DTOs without persistence.
- No source-specific key or HTTP rule leaks into repositories or detectors.

## Completion record

- [x] `NseApiClient` provides equity history, corporate actions, index history,
  EOD report, and optional delivery report operations while owning all NSE HTTP
  headers, URL construction, cookies, session priming, pacing, and retry rules.
- [x] Historical date ranges are split into bounded requests and transport
  failures are classified for access denial, rate limiting, timeouts,
  connection resets, network failures, and server errors.
- [x] Successful responses are checked for empty bodies, unexpected content
  types, malformed JSON, and HTML block pages before parsing.
- [x] Immutable source DTOs and normalization functions validate dates, OHLC,
  volume, delivery data, series, action types, stable event keys, source
  payloads, and checksums without performing persistence.
- [x] Saved fixtures cover valid and empty history, every supported corporate
  action, malformed values, HTML responses, retries, and ISIN-stable symbol
  changes.
- [x] Focused Phase 2 tests and the complete backend test suite pass.

---

# Phase 3 — Ten-year initial backfill

**Status:** Complete — reviewed and verified on 2026-09-04.

## Objective

Import the last ten years of data for every eligible NSE equity in a resumable,
observable job.

## Job entry point

Add a CLI invocation equivalent to:

```text
python -m data_pipeline.cli backfill-history --years 10 --resume
```

Supported options:

- `--from-date`, `--to-date`, or `--years`;
- `--symbol`/`--isin` for targeted recovery;
- `--batch-size` and `--max-securities` for testing;
- `--resume` and `--retry-failed`;
- `--dry-run` to display planned ranges without HTTP/database writes.

## Per-security algorithm

1. Refresh/read `nse_equities` and filter eligible series.
2. Determine the requested ten-year range bounded by listing date.
3. Read the security checkpoint and existing min/max raw bar dates.
4. Split missing coverage into maximum one-year request chunks.
5. Fetch and validate each chunk.
6. Sort and deduplicate bars by trading date.
7. Calculate a deterministic checksum for each normalized source row.
8. Upsert the chunk and update counters in one transaction.
9. Fetch corporate actions over the same historical range.
10. Advance the checkpoint only after committed writes.
11. On a transient error, retry within policy; on final failure, record the
    symbol/range/error and continue to the next security.

## Completeness validation

For each security:

- no duplicate trading dates;
- dates are ordered and inside requested/listing bounds;
- no weekend rows unless explicitly supplied and accepted as a trading day;
- OHLC invariants hold;
- long unexplained gaps are reported, not silently filled;
- row count and coverage dates are stored in the import summary.

## Recovery semantics

- A killed process leaves the run as `RUNNING`; the next invocation marks it
  interrupted and resumes from checkpoints.
- A completed chunk is never downloaded again unless `--force` or a repair
  window requests it.
- A failed security does not roll back successful securities.
- Reprocessing the same source row changes nothing when its checksum matches.

## Exit criteria

- A 5–10 security pilot completes and resumes correctly after forced failure.
- A full run can finish with a queryable list of failed securities.
- Database coverage accurately reports the ten-year window per security.

## Completion record

- [x] `python -m data_pipeline.cli backfill-history` supports explicit date
  ranges, a default ten-year window, targeted symbol/ISIN recovery, batching,
  security limits, resume, failed-only retry, force, and read-only dry runs.
- [x] Normal runs refresh the equity master, select eligible `EQ` securities,
  bound requested history by listing date, and split missing coverage into
  maximum one-year chunks.
- [x] Validated bars are sorted and deduplicated, source checksums make
  unchanged upserts no-ops, and each history chunk and checkpoint commit in
  one bounded database transaction.
- [x] Corporate actions are imported over the requested range with independent
  checkpoints, and completed history/action ranges are not downloaded again
  unless forced.
- [x] Import runs expose progress counters, warnings, partial completion, and a
  queryable per-security failure checkpoint; one failed security does not roll
  back previously committed work.
- [x] Resume closes abandoned running jobs before continuing from checkpoints;
  failed-only recovery selects only securities whose history checkpoint failed.
- [x] Completeness checks enforce range bounds, retain NSE-supplied weekend rows
  with warnings, report long unexplained gaps, and preserve coverage dates and
  row counts in run/checkpoint state.
- [x] Focused Phase 3 recovery/dry-run/transaction tests and the complete
  backend test suite pass.

---

# Phase 4 — Daily delta import and repair window

**Status:** Complete — reviewed and verified on 2026-09-04.

## Objective

Import only new or recently revised data after the initial backfill.

## Job entry point

```text
python -m data_pipeline.cli sync-daily --repair-sessions 10
```

## Algorithm

1. Determine the latest completed NSE trading session. Never ingest the current
   session while its EOD data is incomplete.
2. Refresh the equity master so new listings and symbol changes are known.
3. For an existing security, start from the latest stored date minus ten
   trading sessions.
4. For a newly listed security, import from listing date or the configured
   bootstrap range.
5. Prefer an NSE bulk EOD file when available; fall back to per-security history
   only for missing/rejected rows.
6. Upsert by ISIN/date and compare source checksums to identify revisions.
7. Fetch corporate actions from the last successful action checkpoint minus a
   repair window.
8. Record `changed_from_date` for every affected security.
9. Trigger adjustment, feature, and pattern recomputation only after the source
   transaction commits.

## Scheduling

- Make the command scheduler-agnostic.
- Add a local PowerShell entry point for manual execution.
- Production scheduling occurs after the configured NSE EOD availability time.
- If NSE data is unavailable, retry later and do not advance checkpoints.

## Exit criteria

- Two consecutive runs for the same date produce no duplicate work.
- A corrected bar inside the repair window is detected and propagated.
- A new listing is imported without rerunning the ten-year universe backfill.

## Completion record

- [x] `sync-daily` is scheduler-agnostic and supports repair-session, as-of,
  symbol/ISIN, security-limit, and dry-run options.
- [x] The job selects the latest published EOD report, refreshes the equity
  master on real runs, and falls back to per-security history for missing or
  rejected bulk rows.
- [x] Repair ranges are calculated from stored trading sessions rather than
  calendar-day approximations, while new listings begin at their listing date.
- [x] Bar and corporate-action checksums distinguish inserts, revisions, and
  unchanged rows; identical reruns do not report duplicate source work.
- [x] Per-security checkpoints, run counters, failures, and
  `changed_from_date` are recorded without advancing successful coverage after
  an unavailable source response.
- [x] Downstream recomputation is invoked only after source writes commit.
- [x] Focused Phase 4 tests and the complete backend test suite pass.

---

# Phase 5 — Corporate-action adjustment and data versioning

**Status:** Complete — reviewed and verified on 2026-09-04.

## Objective

Guarantee that every detector consumes one consistent, auditable adjusted
series and that historical backtests can reconstruct what was known at the time.

## Source reconciliation

NSE historical data may already be adjusted for some actions. The implementation
must not blindly apply corporate actions twice.

For a representative fixture set containing splits, bonuses, dividends, and
symbol changes:

1. compare pre/post-action NSE historical values;
2. document which fields/actions NSE already adjusts;
3. set `adjustment_source=NSE_SOURCE` when the supplied series is authoritative;
4. rebuild internally only where required and store the applied factors;
5. retain raw/source-normalized values for audit.

## `AdjustmentService`

Responsibilities:

- order actions by effective date;
- calculate cumulative backward price factors;
- calculate inverse volume factors where applicable;
- apply rounding only after factor calculation;
- write a new adjustment version when the action set or methodology changes;
- return earliest changed adjusted date;
- never mutate the stored source record.

Cash dividends should not be assumed to require the same adjustment as splits
or bonuses. The chosen total-return/price-series policy must be explicit in
configuration and tests.

## Point-in-time requirement

Store source announcement/import timestamps. A historical replay may use an
action only when it was available under the configured point-in-time policy.
This is distinct from producing today's fully adjusted chart.

## Exit criteria

- Golden fixtures reproduce expected adjusted bars for every supported action.
- Rebuilding the same action set produces identical factors/checksums.
- A revised action creates a new data version and invalidates dependent results.

## Completion record

- [x] `AdjustmentService` orders effective-dated actions and builds immutable,
  separately persisted adjusted bars with cumulative backward price factors,
  inverse volume factors, and final-step rounding.
- [x] Split, consolidation, bonus, dividend, rights, buyback, and other action
  behavior is explicit; cash-dividend adjustment is opt-in.
- [x] Configuration defines the methodology version, NSE-source versus
  TradeLens-rebuilt mode, and cash-dividend policy, preventing accidental
  double adjustment of authoritative NSE series.
- [x] Point-in-time action reads filter by source import availability.
- [x] Action-set checksums exclude database lineage, remain deterministic
  across identical rebuilds, and combine with methodology policy to create a
  new adjustment version when inputs or rules change.
- [x] Raw source rows are never mutated; adjusted rows retain source revision,
  adjustment source, factors, and action-set checksum for auditability.
- [x] Golden tests cover all supported action classes, deterministic rebuilding,
  source-authoritative mode, dividend policy, and revised-action invalidation.
- [x] Focused Phase 5 tests and the complete backend test suite pass.

---

# Phase 6 — Common feature engine

## Objective

Compute the complete shared mathematical foundation once so detectors do not
reimplement indicators.

## Migration `009_create_technical_features.sql`

Store one row per ISIN/date/feature version. Include typed columns for commonly
filtered features and `JSONB` only for secondary extensibility.

Typed fields include:

- TR; ATR5/10/14/20/50; NATR14;
- EMA10/20; SMA50/100/200 and configured slopes;
- Range5/10/20/50;
- median volume 5/10/20/50, volume ratio, volume contraction;
- CLV;
- 52-week high/low/range position;
- ATH and price-distance measurements;
- returns 1M/3M/6M/12M;
- RS percentiles/composite when cross-sectional calculation is complete;
- optional delivery fields.

## Calculation details

- TR uses the previous close and handles the first available row explicitly.
- Wilder ATR is seeded consistently and returns unavailable until sufficient
  history exists.
- EMA seeding and SMA window inclusion must be fixed by tests.
- Slopes are percentage-normalized; never store raw rupee slope as the main
  comparison feature.
- Rolling volume uses the median, not mean.
- CLV is `0.5` when high equals low.
- 52-week/ATH breakout reference values exclude the candidate breakout bar.
- Distances use the sign conventions in the specification.
- RS aligns stock and benchmark by trading date, not array index.
- Cross-sectional percentiles use only securities eligible on the as-of date.

## Incremental recomputation

Recompute from `changed_from_date - maximum_feature_lookback`. The initial
maximum is at least 1,260 sessions for five-year breakout support. Persist the
feature/input version so stale rows can be identified.

## Tests

- Hand-calculated golden series for every formula.
- Missing sessions and unequal benchmark calendars.
- Zero-range CLV and zero/invalid denominator handling.
- Insufficient-history behavior.
- Cross-sectional percentile ties.
- Full recomputation equals incremental recomputation.

## Exit criteria

- Every common measurement in sections 8–24 and optional delivery section is
  available to detectors without additional database queries.

## Completion record

- [x] Migration `009_create_technical_features.sql` stores versioned,
  checksummed daily features with typed columns and bounded lookup indexes.
- [x] The append-only `010_extend_feature_and_zone_fields.sql` compatibility
  migration adds current-volume ratio, moving-average distances, deliverable
  volume, median traded value, and explicit zone timing fields without
  rewriting an applied migration.
- [x] Shared calculations cover TR; Wilder ATR5/10/14/20/50; NATR14; EMA and
  SMA values/slopes; price ranges; median-volume normalization; CLV;
  moving-average, 52-week, and all-time-high distances; multi-horizon returns;
  benchmark-aligned relative strength; and optional delivery measurements.
- [x] Rolling price range uses highest high as its denominator, delivery
  expansion uses median delivery percentage 5/20, and zero denominators return
  unavailable values safely.
- [x] Cross-sectional percentile calculation supports the as-of eligible ISIN
  universe and assigns deterministic shared ranks for ties.
- [x] Incremental recomputation uses the 1,260-session dependency window and
  matches full recomputation for every overlapping persisted date.
- [x] Golden and edge-case tests cover indicator seeding, long-window formulas,
  missing/unequal benchmark sessions, insufficient history, flat ranges,
  percentile ties and eligibility, delivery fields, and incremental parity.
- [x] Focused Phase 6 tests and the complete backend test suite pass.

---

# Phase 7 — Swing and price-zone foundations

## Objective

Implement reusable, look-ahead-safe pivots, resistance, support, and buffers.

## Migration `010_create_swings_and_zones.sql`

Create `swing_points` and `price_zones` with input/configuration versioning.

## Swing algorithm

1. Evaluate the configured three-left/three-right pivot window.
2. Record the actual pivot date and price.
3. Set confirmation date to the third subsequent trading session, not calendar
   date plus three days.
4. Compare alternating pivots and discard moves below
   `max(4%, 2 × NATR14)`.
5. Persist raw and meaningful status so tuning can be audited.
6. During replay, expose a swing only when confirmation date is at or before
   the as-of date.

## Zone algorithm

1. Select confirmed meaningful highs or lows in the configured lookback.
2. Calculate tolerance as `clamp(0.5 × NATR14, 0.75%, 2%)`.
3. Cluster compatible prices deterministically.
4. Use cluster median as the zone price.
5. Store dispersion, tests, source swing IDs, and last-test date.
6. Calculate breakout buffer as
   `clamp(0.25 × NATR14, 0.30%, 1%)`.

## Tests

- A pivot is invisible before confirmation and visible on confirmation.
- Trading-holiday confirmation uses sessions, not calendar days.
- Small oscillations are filtered.
- The 499/502/500 example forms one resistance zone around 500.
- Cluster results do not depend on input order.

## Exit criteria

- Detectors can request confirmed swings and zones without calculating them.

## Completion record

- [x] Migration `010_create_swings_and_zones.sql` creates auditable,
  versioned swing and price-zone tables; the append-only extension records
  distinct last-test and confirmation dates.
- [x] The swing engine evaluates three sessions on each side, stores the actual
  pivot and third-subsequent-session confirmation dates, retains raw pivots,
  and marks only alternating moves meeting `max(4%, 2 × NATR14)` meaningful.
- [x] Replay boundaries prevent swings and zones from becoming visible before
  confirmation, including across weekends and non-trading weekdays.
- [x] Resistance and support builders use confirmed meaningful swings within
  the requested lookback, deterministic clustering, median zone price,
  dispersion, test count, stable source swing IDs, and last-test date.
- [x] Zone tolerance uses `clamp(0.5 × NATR14, 0.75%, 2%)`; breakout buffer
  uses `clamp(0.25 × NATR14, 0.30%, 1%)`.
- [x] `SwingZoneService` orchestrates adjusted bars, stored technical features,
  swing calculation, zone construction, and versioned persistence behind the
  repository boundary.
- [x] Repository methods expose bounded, versioned, point-in-time-safe swing
  and zone reads so downstream detectors do not recalculate foundations.
- [x] Tests cover confirmation visibility, trading-session holiday handling,
  small-oscillation filtering, the 499/502/500 resistance example, lookback
  boundaries, and input-order-independent clusters.
- [x] Focused Phase 7 tests and the complete backend test suite pass.

---

# Phase 8 — Supporting pattern detectors

## Review status — complete

Reviewed again after correcting the recorded findings. All 88 backend tests
pass, including the Phase 8/9 acceptance regressions.

- [x] All thirteen supporting identifiers produce dated measurement evidence.
- [x] RS breakout inputs use `context.benchmark_snapshot["bars"]`, containing
  dated benchmark closes. Stock and benchmark sessions align by date; missing
  sessions suppress the affected horizon. Independent 20/50/252-session
  variants handle short stock histories safely and ignore future inputs.
- [x] HHHL durations count supplied trading sessions and pullbacks pair a high
  with its subsequent low. Stage-2 averages use calendar-week closing values.
- [x] The cross-sectional feature helper ranks eligible securities separately
  for each horizon, preserving ties, and stores `rs_1m_percentile` through
  `rs_12m_percentile` in `secondary_metrics`. MOM-RSL exposes the weighted
  10/25/35/30 composite and each contribution. Rank one as-of date per call.
- [x] Inside-bar variants use `COMP-IB1/2/3`; NR7 compares percentage ranges;
  configurable MA conditions include SMA100; momentum acceleration exposes a
  continuous bounded score and contributions.
- [x] Positive, negative, missing-data and boundary fixtures exercise supporting
  rules with matching as-of dates, including independent RS horizons, equal
  ranges, equal momentum pace, threshold equality, and replay isolation.

Integration contract: supply benchmark bars and ranked per-horizon feature
fields to the pure detector service. Universe scheduling and candidate
persistence belong to the later orchestration/lifecycle phases.

## Objective

Implement the reusable technical state that primary patterns and context scores
consume.

## Detector contract

```text
detect(security, bars, features, swings, zones, context) -> candidates
```

Each candidate must include its measurement evidence and as-of date.

## Detectors

- `BASE-TIGHT`: Range10, ATR5/ATR20, volume5/volume20, close dispersion,
  inside-bar count.
- `TREND-HHHL`: higher-high ratio, higher-low ratio, trend duration, average
  pullback depth/duration, normalized slope.
- `TREND-S2`: close/30-week MA, rising 30-week MA, SMA50/SMA200 alignment,
  slopes, range position, RS.
- `TREND-MA`: score all configured MA alignment and slope conditions to 0–100.
- `COMP-NR7`: today's daily range is the smallest of the inclusive seven-bar
  window.
- `COMP-IB`: detect one to three consecutive inside bars and derive variants.
- `COMP-ATR`: ATR5/ATR20, ATR10/ATR50, one-year ATR percentile.
- `COMP-RANGE`: Range5/Range20 and Range10/Range50.
- `MOM-ACC`: 21/63/126/252-session returns and normalized monthly pace.
- `MOM-RSL`: cross-sectional RS percentiles and weighted composite.
- `MOM-RSB`: stock/benchmark relative-price highs over 20/50/252 sessions.
- `VOL-DRY`: median volume5/median volume50 and strength band.
- `VOL-EXP`: current volume/median volume20 and strength band.

Optional delivery measurements remain supporting evidence and must never be
described as institutional buying.

## Exit criteria

- Every supporting identifier in the specification has fixtures for true,
  false, insufficient-data, and boundary-threshold cases.

---

# Phase 9 — Primary base detectors

## Review status — complete

Reviewed again after correcting the recorded findings. All 88 backend tests
pass, including duration, geometry and successive-session regressions.

- [x] All three base families expose geometry, pivots, support, invalidation
  and named quality contributions; VCP also exposes maturity contributions.
- [x] VCP searches recent suffixes of two through five contractions, allowing
  a recent eligible base even when an older contraction is outside the window.
- [x] A progressing base followed by excessive contraction expansion emits
  INVALIDATED evidence; the progression filter no longer hides that failure.
- [x] Flat-base depth/flatness breaks retain invalidation evidence when the
  preceding window satisfied the geometry limits. Invalidated candidates take
  precedence over competing active windows in the same scan.
- [x] Resistance candidates must fall within the zone's percentage tolerance
  of the final swing high. Distant historical resistance is excluded.
- [x] Flat-base dispersion uses population standard deviation divided by mean
  of the supplied source swing prices. Missing source evidence remains null.
- [x] Tests cover VCP counts 2–5, exact 20/90-session and 8/35-percent limits,
  flat-base 20/60-session and 15-percent limits, near-high 20/80-session windows
  and 60-percent persistence, progression equality, and trigger equality.
- [x] Separate session advances verify READY, TRIGGERED, CONFIRMED and
  INVALIDATED evidence. Replay tests exclude unconfirmed swings and future
  inputs; confirmation requires the final contraction to have been known on
  the earlier confirming session.

Candidate evidence remains side-effect free. Persisted instance matching,
terminal-state retention and event history remain owned by Phase 13.

## Objective

Implement `BASE-FLAT`, `BASE-52WH`, and `BASE-VCP` with complete geometry,
quality, maturity, pivot, and invalidation evidence.

## `BASE-FLAT`

- Search configurable 20–60 session candidate windows.
- Calculate depth and reject above configured maximum.
- Require at least two resistance-zone and two support-zone interactions.
- Calculate resistance/support dispersion.
- Run OLS on closes and normalize total fitted move by mean close.
- Calculate early/late ATR and volume compression.
- Pivot is the median resistance-zone price.
- READY requires configured pivot distance, depth, and quality.
- Invalidate below support tolerance or when depth/flatness breaks.

## `BASE-52WH`

- Use the previous 252-session high, excluding the current session.
- Search configurable 20–80 session consolidation windows.
- Calculate depth and fraction of closes within the near-high threshold.
- Require persistence ratio at or above the configured default.
- Score proximity, persistence, depth, compression, RS, and trend.
- Derive READY and strong-ready evidence separately.

## `BASE-VCP`

- Search configurable 20–90 session windows with 8–35% depth.
- Use alternating confirmed swing highs/lows.
- Extract two to five contractions and calculate every contraction percentage.
- Evaluate contraction ratios, final contraction, low progression with
  `0.5 × ATR14` tolerance, ATR compression, and volume compression.
- Choose the final swing high or resistance-cluster median as pivot.
- Calculate pivot distance and base low/invalidation.
- Derive `VCP-2C` through `VCP-5C` variants.
- Implement DETECTED, FORMING, MATURE, READY, TRIGGERED, and CONFIRMED evidence.
- Invalidate on base-low break, excessive contraction expansion, or configured
  SMA50/slope deterioration.

## Exit criteria

- Every score component is individually visible in candidate measurements.
- Boundary tests cover exact minimum/maximum duration, depth, contraction count,
  threshold equality, and one-session state transitions.

---

# Phase 10 — Breakout detectors

## Review status — complete

Reviewed against the canonical breakout rules after correcting the recorded
findings. All 103 backend tests pass, including focused Phase 10/11 replay and
event-time regressions.

- [x] BRK-RANGE, BRK-52WH, BRK-ATH, and all BRK-MULTIY variants use
  the same breakout core; adapters provide only pivot/source metadata.
- [x] Prior-high calculations exclude the current session. Range resistance
  requires a confirmed zone with at least two tests and 20–120-session age.
- [x] Multi-year variants use 504/756/1,260-session windows and record the age
  of the latest qualifying historical resistance test plus historical count.
- [x] The strict buffered-close boundary, ATR magnitude, VolumeRatio20, CLV,
  range expansion, extension flag, and named quality contributions are
  recorded. Breakout-candle quality remains anchored to the trigger session.
- [x] Optional originating base evidence is matched point-in-time by security
  and pivot proximity and contributes independently from resistance quality.
- [x] The first valid buffered close is always TRIGGERED. Confirmation cannot
  occur until a later session and requires two closes above pivot or a strong
  breakout close whose next session does not fail.
- [x] Five-session failure monitoring uses the buffered pivot. FAIL-BRK
  records breakout-candle and failure-session volume separately and marks
  strong failure only when both price and failure-volume rules pass.
- [x] Tests cover equality at the breakout threshold, a valid cross following
  an intermediate close above pivot, trigger-to-confirm/fail transitions,
  stable trigger evidence, source-base linkage, historical resistance age,
  incomplete history, and future-input isolation.

Candidate persistence, terminal-state retention, and event history remain
owned by Phase 13.

## Objective

Build one generic breakout engine and reuse it for different resistance sources.

## Generic breakout engine

Inputs include pivot source, zone quality, source base, and lookback. Calculate:

- buffered close above pivot;
- breakout magnitude in ATR;
- volume ratio20;
- CLV;
- daily range/ATR expansion;
- extended status at the earlier of pivot + 2 ATR or pivot + 5%;
- quality components and source-base linkage.

## Variants

- `BRK-RANGE`: clustered resistance with two or more tests in 20–120 sessions.
- `BRK-52WH`: previous 252-session high.
- `BRK-ATH`: highest prior adjusted high; require sufficiently complete history.
- `BRK-MULTIY`: common family implemented through `BRK-2Y`, `BRK-3Y`, and
  `BRK-5Y` variants using 504/756/1,260-session resistance with age and
  historical test count.

## Lifecycle

- First valid close is TRIGGERED.
- Two closes above pivot, or configured strong-close follow-through, confirms.
- Observe five sessions for failure by default.
- Emit `FAIL-BRK` when close returns below buffered pivot; store strong-failure
  evidence when breakout-candle low and volume conditions are met.

## Exit criteria

- All variants call the same breakout core and differ only by pivot source and
  variant metadata.

---

# Phase 11 — Pullback detectors

## Review status — complete

Reviewed against the canonical pullback requirements after correcting
event-time, source-linkage, and variant-identifier gaps. The complete
103-test backend suite passes.

- [x] PB-BRKRET accepts only persisted, confirmed, same-security breakout
  instances visible at the replay as-of date and records their instance ID,
  type, variant, pivot, breakout date, and original quality.
- [x] Maximum advance satisfies both sides of max(3%, 1 × ATR14) using
  breakout-date ATR. Retest touches before session three are ignored; the
  valid 3–30 and preferred 5–20 windows are measured from the breakout.
- [x] Breakout retests use the configured NATR clamp, pullback volume evidence,
  FORMING/READY/TRIGGERED states, conservative buffered retest-high trigger,
  and both specified invalidation paths.
- [x] PB-EMA20 validates EMA20/SMA50/SMA200 alignment, positive slopes, 10 of
  15 prior closes, 3–12% depth, 2–10-session duration, clamped touch proximity,
  pullback volume, closing behavior, two-session trigger, and persistent or
  structural invalidation.
- [x] PB-SMA50 validates SMA50/SMA200 trend requirements, 70% of 40 prior
  closes, 5–20% depth, 3–20-session duration, bounce and invalidation rules.
  Distinct 126-session touch episodes are separated by at least ten sessions.
- [x] SMA50 variants use the stable identifiers PB-SMA50-T1, PB-SMA50-T2,
  and PB-SMA50-T3+.
- [x] Moving-average candidates preserve supplied trend identifiers and record
  their confirmed source swing and prerequisite evidence without inventing
  unsupported pattern links.
- [x] EMA20 invalidation and a separate SMA50 candidate coexist in one scan.
  Tests also cover conservative triggers, source confirmation visibility,
  early-retest exclusion, breakout-ATR anchoring, touch episodes, and future
  swing/bar isolation.

Lifecycle deduplication, expiry after maximum duration, and persisted source
state transitions remain owned by Phase 13.

## `PB-BRKRET`

- Requires a persisted confirmed source breakout.
- Require maximum advance of `max(3%, 1 ATR14)` before retest.
- Allow retest 3–30 sessions after breakout; score preferred 5–20 window.
- Use NATR-clamped retest tolerance and reduced pullback volume.
- FORMING starts with pullback, READY on entering zone, TRIGGERED on conservative
  close above retest swing high plus buffer.
- Invalidate after two closes below tolerance or one close below pivot − ATR14.

## `PB-EMA20`

- Require EMA20/SMA50/SMA200 alignment and positive slopes.
- Verify at least 10 of the prior 15 closes above EMA20 before pullback.
- Enforce 3–12% depth, 2–10 session duration, touch tolerance, and volume ratio.
- Prefer close at/above EMA20 and CLV at/above configured level.
- Trigger above the highest high of the prior two sessions after a valid touch.
- Invalidate on persistent/significant EMA20 penetration or structural-low break.

## `PB-SMA50`

- Require SMA50 above SMA200 and rising.
- Require price above SMA50 for 70% of the previous 40 sessions.
- Enforce 5–20% depth, 3–20 session duration, touch tolerance, and volume ratio.
- Count distinct touch episodes over 126 sessions separated by at least ten
  sessions and derive `T1`, `T2`, `T3+` variants.
- Trigger on the configured bounce; invalidate on two significant closes below
  SMA50 or slope plus structural failure.

## Exit criteria

- Pullback candidates link to their originating trend/breakout evidence.
- EMA20 failure can coexist with a newly forming SMA50 candidate without
  mutating one pattern into the other.

---

# Phase 12 — Failure detectors

## Review status — complete

Reviewed against the Phase 12 detector rules and exit expectations on
2026-09-05. The implementation is complete.

- [x] `FAIL-BRK` records the original pivot, maximum post-breakout advance,
  sessions above pivot, failure depth and volume, breakout-candle failure, and
  relative-strength deterioration.
- [x] `FAIL-BASE` uses the source instance's exact invalidation price when it is
  available and otherwise applies the recorded/configured support tolerance.
- [x] `FAIL-EMA20` requires two closes below EMA20 plus greater-than-one-ATR
  penetration or a confirmed meaningful swing-low break.
- [x] `FAIL-SMA50` requires two closes below SMA50 with at least one-ATR
  penetration and records non-positive slope as stronger failure evidence.
- [x] `FAIL-STRUCT` uses the latest point-in-time-visible confirmed meaningful
  swing low.
- [x] Every failure candidate links its source pattern instance when one exists,
  while source lifecycle mutation remains outside the detectors.
- [x] Boundary, evidence, source-link, invalidation-precedence, and
  point-in-time regression tests pass.

Implement independent candidates for:

- `FAIL-BRK` with original pivot, maximum advance, days above pivot, failure
  depth/volume, breakout-candle break, and RS deterioration;
- `FAIL-BASE` below support tolerance;
- `FAIL-EMA20` after two closes plus ATR penetration or swing-low break;
- `FAIL-SMA50` after two closes by at least one ATR, strengthened by non-positive
  slope;
- `FAIL-STRUCT` below the previous confirmed meaningful swing low.

Failure detectors must reference the source pattern instance when one exists.
They create evidence; lifecycle rules decide which source instance becomes
FAILED or INVALIDATED.

---

# Phase 13 — Scoring, context, and lifecycle persistence

## Review status — complete

Reviewed against the Phase 13 migration, scoring, lifecycle, and exit criteria
on 2026-09-05. The implementation is complete.

- [x] Migration `011_create_pattern_tables.sql` defines versioned pattern
  instances, bounded scores, geometry, lineage, active deduplication, and an
  append-only event timeline with database-enforced update/delete rejection.
- [x] Reusable bounded weighted scoring returns named contributions; context
  measures market, sector, trend, relative strength, volume, and liquidity
  independently from detector geometry.
- [x] Setup scoring uses the configured `35/20/15/15/10/5` weighting and
  maturity scores map across all configured display-band boundaries.
- [x] Lifecycle matching reuses overlapping same-security/same-type instances
  within pivot tolerance, so daily scans update instead of duplicating rows.
- [x] Backward transitions are rejected, terminal states cannot be updated, and
  optimistic state versions protect concurrent persistence.
- [x] Meaningful state, pivot, score, maturity, and terminal changes are stored
  atomically with reconstructable previous/new event values.
- [x] Trigger and confirmation dates retain their actual effective dates,
  including candidates first persisted in `CONFIRMED` state.
- [x] Base, breakout-retest, EMA20-pullback, and SMA50-pullback expiry uses
  configured trading-session limits.
- [x] Focused Phase 12/13 tests and the complete backend suite pass: 123 tests.

## Migrations

### `011_create_pattern_tables.sql`

Create `pattern_instances` with:

- UUID, ISIN, class/type/variant;
- start, detection, trigger, confirmation, last-update, terminal dates;
- state and state version;
- quality, maturity, context, setup scores constrained to 0–100;
- pivot, support, invalidation;
- source pattern ID;
- measurements/supporting patterns as JSONB;
- configuration, engine, feature, and adjustment versions;
- active deduplication key.

Create `pattern_events` with immutable previous/new state/value payload and
effective/recorded timestamps.

## Scoring

- Implement a reusable bounded component-score helper.
- Return total plus named component contributions.
- Keep quality and maturity calculators pattern-specific.
- Context calculates market regime, sector strength, trend, RS, volume, and
  liquidity independently of geometry.
- Setup uses the configured 35/20/15/15/10/5 default weighting.
- Map maturity 0–39/40–64/65–79/80–89/90–100 to the configured display bands.

## Lifecycle algorithm

Persist and expose the specification's complete lifecycle vocabulary:
`DETECTED`, `FORMING`, `MATURE`, `READY`, `TRIGGERED`, `CONFIRMED`, `FAILED`,
`INVALIDATED`, and `EXPIRED`. Each detector declares the subset and allowed
transitions it uses; the lifecycle service rejects impossible or backward
transitions. `FAILED`, `INVALIDATED`, and `EXPIRED` are terminal unless a later
specification version explicitly defines otherwise.

1. Load active same-security/same-type patterns.
2. Match candidates by overlapping window and similar base/pivot tolerance.
3. Create when no match exists.
4. Update the matched instance without erasing previous events.
5. Emit events only for meaningful state, pivot, score, or terminal changes.
6. Never move backwards from terminal states.
7. Expire bases after maximum duration without updated structure.
8. Expire breakout retests after 30 sessions and pullbacks after configured
   maximum duration.

## Exit criteria

- Daily scans do not create one pattern row per day.
- Complete timelines can reconstruct every material transition.
- Geometry detection is unchanged when market-context input changes; only
  context/setup ranking changes.

---

# Phase 14 — Engine orchestration and incremental execution

## `PatternEngineRunner`

For every affected security/as-of date:

1. load adjusted bars and feature series;
2. validate minimum history and liquidity metadata;
3. load confirmed swings and zones;
4. run supporting detectors;
5. run base detectors;
6. run breakout detectors;
7. run pullback detectors;
8. run failure detectors;
9. score candidates;
10. calculate context/setup score;
11. pass candidates to lifecycle service;
12. persist instances/events in one security-scoped transaction.

Execution must support:

- one security/date for debugging;
- changed securities after daily import;
- whole-universe scan;
- historical replay without writing live pattern tables;
- dry-run output containing all measurements and rule decisions.

Persist run-level metrics and failed securities. One malformed security must not
abort the universe scan.

---

# Phase 15 — Protected APIs and product UI

## APIs

Add thin handlers/services for:

- `GET /api/overview`: market summary and ranked active opportunities;
- `GET /api/setups`: pagination and filters for class, type, variant, state,
  score ranges, sector, RS, liquidity, and as-of date;
- `GET /api/securities/{isin}/fingerprint`;
- `GET /api/patterns/{id}`;
- `GET /api/patterns/{id}/events`;
- later `GET /api/research/patterns/...`.

All endpoints require a valid bearer token. Repository queries must paginate and
use typed filters; do not load the full universe into the HTTP handler.

## Overview UI

Replace placeholders with:

- EOD freshness/import status;
- market regime and breadth summary;
- counts by READY, TRIGGERED, CONFIRMED, FAILED;
- highest-ranked setups;
- filters for setup family, state, score, sector, and liquidity;
- explicit “ranking, not probability” language.

## Technical fingerprint UI

Display:

- trend and moving-average state;
- primary pattern and variant;
- lifecycle state and maturity band;
- quality, maturity, context, and setup scores separately;
- compression, momentum, RS, volume, and location measurements;
- pivot, support, invalidation, and distance values;
- supporting patterns;
- event timeline and data/configuration version.

Follow `topology.css`, mobile breakpoints, JWT route protection, and sign-out
history replacement defined in `AGENTS.md`.

---

# Phase 16 — Backtesting and historical research

## Migrations

Create `backtest_runs`, `backtest_entries`, and `backtest_outcomes` with engine,
configuration, universe, point-in-time data policy, and status metadata.

## Replay engine

- Advance one trading session at a time.
- Expose only bars/actions/memberships/pivots available as of that date.
- Reconstruct the eligible universe from effective-dated security and index
  membership records on each replay date. Do not backtest only today's listed
  securities; this is the explicit control for survivorship bias.
- Exclude the current bar from breakout reference highs.
- Run the same detectors/scorers used in production.
- Record triggered entry date/price and complete candidate fingerprint.

## Outcomes

Calculate:

- returns at 5/10/20/40/60 sessions;
- MFE and MAE over each configured horizon;
- days to +5%, +10%, +20%;
- hit +5 before −5, +10 before −8, and +20 before −8;
- sample counts and missing/future-data completeness.

Research queries must support combinations such as VCP + RS6M threshold + Stage
2 + sector/market threshold + volume compression. Historical probability is
shown only from adequate samples and never inferred from setup score.

---

# Phase 17 — Operations, monitoring, and production hardening

## Metrics and logs

Record structured fields for run ID, job type, ISIN, symbol, requested range,
attempt, duration, rows, source status, and error class. Never log cookies,
credentials, JWTs, or raw authorization headers.

Monitor:

- NSE request success/rate-limit/block rates;
- last successful equity/history/action/delta run;
- securities and bars imported/rejected;
- missing-date anomalies;
- adjustment/feature/pattern lag;
- active patterns/events created;
- per-stage runtime and failed securities.

## Operational commands

Provide commands for:

- import plan/dry run;
- ten-year backfill/resume/retry failures;
- daily sync;
- rebuild one security's adjustments/features/patterns;
- rebuild by date range/version;
- validate database coverage;
- run one detector with explanation output;
- run and resume a backtest.

## Performance policy

Start with standard-library calculations and database batching. Benchmark a
realistic universe before adding numeric dependencies. Add NumPy or another
dependency only if profiling demonstrates a material bottleneck and tests prove
identical output.

## Exit criteria

- A failed daily run is visible and safely recoverable.
- Data lineage from displayed pattern to source bars/actions/config is queryable.
- Full daily processing finishes within the agreed post-market processing
  window.

---

# 18. Cross-phase testing strategy

## Unit tests

- Formula and threshold boundary tests.
- Parser and response-validation tests.
- Each detector's true/false/insufficient-history cases.
- Score-component and state-transition tests.

## Repository tests

- Migration application from empty database.
- Upsert idempotency and checkpoint transactions.
- Pattern deduplication and immutable events.
- Pagination/filter query behavior.

## Integration tests

- Fixture NSE response → raw rows → adjusted rows → features.
- Adjusted series → swing/zone → candidate → persisted instance/event.
- Daily correction/action revision → targeted downstream recomputation.
- JWT-protected overview and fingerprint APIs.

## Golden scenario tests

Maintain synthetic named datasets for:

- VCP-2C through VCP-5C;
- valid/invalid flat and 52-week-high bases;
- each breakout source and failed breakout;
- breakout retest state sequence;
- EMA20/SMA50 pullback and failure;
- all supporting signals;
- action-adjusted history and look-ahead traps.

Each fixture must describe why it should or should not detect, expected pivot,
state, measurements, and scores.

## Non-functional tests

- Resume after process termination.
- Duplicate daily run.
- NSE block/timeout/retry.
- Six-plus million row backfill volume benchmark.
- Full-universe daily runtime benchmark.
- 320px/390px frontend width and keyboard accessibility checks.

## Phase 18 implementation assets

- `test_cross_phase_strategy.py` covers the reviewed Reliance NSE payload from
  parsing through adjustment/features, correction recomputation, and the
  swing/detector/lifecycle persistence boundary.
- `fixtures/golden/pattern_scenarios.json` is the machine-validated V1 scenario
  inventory and explanation contract.
- `test_live_nse_contract.py` and `data_pipeline.cli verify-nse-contract` provide
  the opt-in exchange contract gate without making deterministic CI depend on
  NSE availability.
- `benchmarks.phase18` supplies the bounded-memory six-million-row ingestion
  benchmark; `operations.cli benchmark-scan` supplies the production detector
  universe benchmark.
- `src/doc/cross_phase_testing_strategy.md` defines execution, provenance,
  responsive/accessibility gates, and failure interpretation.

# 19. Phase dependencies and delivery gates

| Phase | Depends on | Gate before proceeding |
|---|---|---|
| 0 Contracts/config | Existing code | Config and domain types tested |
| 1 Schema | Phase 0 | Idempotent migrations/repositories |
| 2 NSE client | Phase 0 | Fixture parsers and HTTP failures tested |
| 3 Backfill | 1–2 | Resumable pilot import |
| 4 Daily delta | 1–3 | Idempotent delta and repair window |
| 5 Adjustments | 1–4 | Golden corporate-action fixtures |
| 6 Features | 5 | Formula parity and incremental equality |
| 7 Swings/zones | 6 | Confirmation/look-ahead tests |
| 8 Supporting | 6–7 | Full supporting inventory covered |
| 9 Bases | 6–8 | Base geometry and states covered |
| 10 Breakouts | 7–9 | Generic engine and failure window |
| 11 Pullbacks | 7–10 | Source linkage and invalidation |
| 12 Failures | 8–11 | All failure identifiers covered |
| 13 Scores/lifecycle | 8–12 | Deduplication and immutable timeline |
| 14 Orchestration | 3–13 | Incremental universe scan |
| 15 API/UI | 13–14 | Explainable protected user flow |
| 16 Backtesting | 0–14 | Point-in-time replay parity |
| 17 Operations | All earlier | Recoverable monitored production jobs |

# 20. Recommended delivery milestones

## Milestone A — Trustworthy market-data foundation

Phases 0–5. Result: ten-year resumable backfill, daily delta import, corporate
actions, and versioned adjusted bars.

## Milestone B — Explainable technical foundation

Phases 6–8. Result: features, confirmed swings/zones, and supporting technical
state for every eligible security.

## Milestone C — First end-to-end product slice

Phases 9, 13–15 for `BASE-FLAT` first. Result: one primary pattern flows from
adjusted data to persisted lifecycle/events and the authenticated overview.

## Milestone D — Full V1 detector inventory

Phases 9–12. Result: all base, breakout, pullback, supporting, and failure
patterns in the specification.

## Milestone E — Evidence and calibration

Phases 16–17. Result: backtesting, research filters, operational monitoring,
and threshold calibration without changing deterministic detector semantics.

# 21. Final definition of done

The implementation is complete only when:

- the full NSE universe has auditable ten-year adjusted history;
- daily delta processing updates only affected securities and repairs revisions;
- every input, threshold, calculation, and score is versioned and explainable;
- all primary, supporting, and failure patterns in the specification exist;
- swing confirmation and historical replay are free of known look-ahead bias;
- active patterns deduplicate while every lifecycle transition remains stored;
- users can inspect a technical fingerprint, trigger, pivot, invalidation, and
  event timeline;
- setup score is clearly separated from historical outcome probability;
- backtests use the production detector code and provide the required outcome
  measurements;
- imports/scans can be resumed, monitored, and selectively rebuilt;
- tests cover formulas, patterns, lifecycle, source failures, point-in-time
  behavior, APIs, and responsive UI.

# 22. Decisions to lock before production implementation

These items are deliberately explicit because silently choosing them would
change historical results:

1. Confirm from sampled NSE responses exactly which actions are already
   reflected in historical OHLCV, so TradeLens never double-adjusts data.
2. Decide whether cash dividends produce a price adjustment or whether V1 uses
   split/bonus-adjusted price history only.
3. Confirm the canonical NSE endpoint/report for daily bars, delivery data,
   benchmark history, sector history, and corporate actions, including fallback
   behavior when a report is late.
4. Define eligible security series (`EQ`, `BE`, SME, ETFs, preference shares,
   and suspended/delisted securities) independently for detection, ranking, and
   backtesting.
5. Define the commercial liquidity universe; the specification's ₹20 price,
   250-session history, and ₹2 crore median traded-value examples remain
   configurable defaults until validated.
6. Select NIFTY 500 as the initial broad benchmark or record the approved
   replacement in configuration.
7. Define the authoritative sector taxonomy and effective-dated membership
   source used for sector strength and historical replay.
8. Resolve the specification's `BRK-BASE` retest source label: either make it a
   documented alias for a base-linked `BRK-RANGE` or add it as a stable pattern
   identifier before persistence/API contracts are frozen.
9. Define the post-market schedule, maximum acceptable daily runtime, NSE
   request-rate budget, and alert destination.
10. Define retention policy for source payloads and old adjustment/feature
    versions after backtests have recorded their lineage.

# 23. Pattern inventory traceability checklist

The implementation cannot declare V1 complete until the following inventory
has detector, boundary, lifecycle, serialization, and explanation tests.

## Primary setups

- `BASE-VCP` with `VCP-2C`, `VCP-3C`, `VCP-4C`, `VCP-5C`.
- `BASE-FLAT`.
- `BASE-52WH`.
- `BRK-RANGE`, `BRK-52WH`, `BRK-ATH`, and `BRK-MULTIY` through `BRK-2Y`,
  `BRK-3Y`, `BRK-5Y`.
- `PB-BRKRET`.
- `PB-EMA20`.
- `PB-SMA50` through `PB-SMA50-T1`, `PB-SMA50-T2`, `PB-SMA50-T3+`.

## Supporting patterns/signals

- `TREND-HHHL`, `TREND-S2`, `TREND-MA`.
- `BASE-TIGHT`.
- `COMP-NR7`, `COMP-IB1`, `COMP-IB2`, `COMP-IB3`, `COMP-ATR`, `COMP-RANGE`.
- `MOM-ACC`, `MOM-RSL`, `MOM-RSB`.
- `VOL-DRY`, `VOL-EXP`.

## Failure patterns

- `FAIL-BRK`, `FAIL-BASE`, `FAIL-EMA20`, `FAIL-SMA50`, `FAIL-STRUCT`.

## Lifecycle states

- `DETECTED`, `FORMING`, `MATURE`, `READY`, `TRIGGERED`, `CONFIRMED`,
  `FAILED`, `INVALIDATED`, and `EXPIRED`.

# 24. Multi-timeframe scanner delivery

Pattern discovery is a separate administrator activity from history download.
It records the requested intervals and pattern groups on the parent run, then
rebuilds derived adjusted data and invokes the shared runner without requesting
new NSE history. Resume preserves the original interval selection.

Completed work:

- scanner API and UI filters for 1D, 1W, and 1M;
- persisted timeframe, family, direction, and interval-completion metadata;
- completed-week and completed-month aggregation from adjusted daily bars;
- point-in-time REV-DBOT and REV-DTOP detectors and fixtures;
- measured HARM-ABCD detection and fixtures;
- administrator-only POST /api/admin/pattern-scans activity.

Each later family must add configuration, pure detectors, golden fixtures,
runner integration, lifecycle evidence, and scanner labels in one coherent
change. Harmonic ratios remain measurements with configured tolerances; the
client must never infer them from chart pixels.
