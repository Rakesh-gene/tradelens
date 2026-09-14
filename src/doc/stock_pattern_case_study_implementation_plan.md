# Stock Pattern Case Study Implementation Plan

## Purpose

TradeLens should provide reproducible stock case studies that explain how a
pattern was identified using information available at the time and show how
the adjusted stock price performed over positional holding horizons.

Case studies are historical research evidence. They are not recommendations,
probability claims, or proof that a current setup will produce the same result.
They must follow the point-in-time, adjusted-price, lifecycle, and versioning
rules in `positional_trading_pattern_engine_spec.md`.

## Accepted positional-outcome correction (2026-09-14)

The primary case-study outcome is the stock's adjusted forward performance,
not hypothetical trade profit. Anchor performance to the next trading
session's adjusted open after the EOD pattern signal, then report the adjusted
close return, maximum advance, and maximum drawdown after approximately three
months (63 sessions), six months (126 sessions), and one year (252 sessions).
Show the exact observation date and explicitly label incomplete horizons.

The annotated adjusted-price chart and the versioned reasons the pattern
qualified must precede the forward outcomes. Stop, target, position sizing,
cost, and P/L simulation may remain stored as secondary research lineage, but
must not define the catalog cards, representative-case ranking, or principal
case-study narrative.

## Existing foundation

The repository already provides:

- point-in-time detector replay using the production detector and scorer path;
- `backtest_runs`, `backtest_entries`, and `backtest_outcomes` persistence;
- authenticated research run and result APIs;
- 5, 10, 20, 40, and 60-session returns;
- maximum favorable excursion (MFE) and maximum adverse excursion (MAE);
- days-to-threshold and hit-before-loss outcomes;
- engine, configuration, feature, adjustment, and universe-policy lineage.

The case-study feature should reuse these capabilities. It needs a versioned
forward-performance policy, deterministic case selection, case-study
persistence, a separate pipeline activity, and dedicated user-facing screens.

## 1. Versioned positional-performance policy

Every case study must store the entry anchor, observation dates, adjusted
prices, horizon completeness, and calculation lineage.

### Entry

- The pattern must reach `TRIGGERED` or `CONFIRMED`.
- An end-of-day signal becomes known only after the detection-session close.
- The default hypothetical entry is the next trading session's adjusted open.
- The next session's adjusted open is the common comparison anchor, not a
  simulated order fill or recommendation.

### Forward performance

Store and display for 63, 126, and 252 trading sessions:

```text
Forward return % = (Horizon adjusted close / Entry anchor - 1) * 100
Maximum advance = max adjusted high relative to the entry anchor
Maximum drawdown = min adjusted low relative to the entry anchor
```

Do not substitute a partial-window return for a completed horizon. Show partial
history separately as performance to date and label the horizon `Pending`.

## 2. Case-study selection policy

Case selection must be deterministic and must not cherry-pick only rising
examples.

Build a stratified catalog across:

- pattern type and variant;
- daily, weekly, and monthly timeframes;
- bullish and bearish directions;
- strong, neutral, and weak market regimes;
- strong and weak sector context;
- positive, median, negative, and incomplete forward-price outcomes.

For each supported pattern and timeframe combination, select representative
cases by the longest available forward-return horizon using a stable rule:

1. highest forward adjusted-price return;
2. median forward adjusted-price return;
3. lowest forward adjusted-price return;
4. first incomplete forward window when one exists.

Tie-break using entry date, ISIN, and replay fingerprint. Store the selection
policy version so the catalog can be reproduced.

### Initial pattern coverage

Start with detectors that currently produce validated results:

- `BASE-VCP`, `BASE-FLAT`, and `BASE-52WH`;
- `BRK-RANGE`, `BRK-52WH`, `BRK-ATH`, and `BRK-MULTIY`;
- `PB-BRKRET`, `PB-EMA20`, and `PB-SMA50`;
- `REV-DTOP` and `REV-DBOT`;
- `HARM-ABCD`.

Add flags, pennants, triangles, wedges, other reversal structures, and other
harmonic families only after their detectors, point-in-time fixtures, and
production persistence are complete.

Use `RELIANCE` / `INE002A01018` as the cross-phase contract example. Choose the
remaining real-stock cases from replay output using the deterministic selection
policy rather than maintaining a hand-picked winner list.

## 3. Separate pipeline activity

Add an administrator activity named **Case Study Build**. It must remain
separate from pattern discovery and historical research runs.

Execute these stages in dependency order:

1. validate adjusted-price and feature coverage;
2. run point-in-time historical replay;
3. select eligible triggered patterns;
4. anchor the case at the next session's adjusted open;
5. calculate 3M, 6M, and 1Y return, maximum advance, maximum drawdown, and
   horizon completeness;
6. select representative cases using the configured selection policy;
7. persist case-study facts and chart annotations;
8. record incomplete, skipped, and ambiguous cases explicitly.

The activity must be asynchronous, resumable, incremental, and isolated by
security. It should support one security, an explicit bounded selection, and a
deliberate universe run. A failed security must not abort the entire run.

Rebuild a case when its engine version, configuration version, feature version,
adjustment version, trade-policy version, or selection-policy version changes.

## 4. Persistence

Add append-only migrations for the following tables.

### `case_study_runs`

Store:

- run ID and status;
- requested date range and universe;
- requested pattern types and timeframes;
- engine, configuration, feature, and adjustment versions;
- positional-performance and selection-policy versions;
- progress counts, timing, failure summary, and initiating user;
- point-in-time and survivorship-bias policies.

### `case_studies`

Store:

- stable case-study ID;
- source backtest run and entry IDs;
- ISIN and historical symbol/company identity;
- pattern type, variant, group, direction, timeframe, and lifecycle state;
- pattern start, detection, trigger, confirmation, and entry-anchor dates;
- entry anchor, pivot, support, and invalidation prices;
- pattern measurements and supporting evidence;
- market, sector, relative-strength, and liquidity context;
- horizon completeness and review status;
- complete calculation lineage.

### Case-study outcome data

Store:

- entry anchor date and adjusted open;
- 3M, 6M, and 1Y observation dates, closes, returns, and completeness;
- maximum advance and maximum drawdown per completed horizon;
- performance-to-date facts for incomplete horizons.

Do not duplicate adjusted candles. Retrieve them through the existing market
data repository using the case's adjustment version.

## 5. Service boundaries

Add focused modules rather than placing simulation logic in HTTP handlers or
React components:

```text
src/backend/pattern_engine/positional_performance.py
src/backend/pattern_engine/case_study_selection.py
src/backend/pattern_engine/case_study_service.py
src/backend/repositories/case_studies.py
src/backend/operations/case_study_pipeline.py
```

- `positional_performance.py` owns the next-session anchor and deterministic
  63/126/252-session performance calculations.
- `case_study_selection.py` owns stratification and deterministic selection.
- `case_study_service.py` owns queries and browser-facing contracts.
- repositories own SQL and transactions.
- the pipeline owns orchestration, progress, retry, and failure isolation.
- React renders server-supplied facts and does not recalculate returns.

## 6. API surface

Add authenticated product endpoints:

| Method and path | Purpose |
| --- | --- |
| `GET /api/case-studies` | Filtered, sorted, cursor-paginated case summaries |
| `GET /api/case-studies/{id}` | Complete detection, rationale, positional performance, and lineage evidence |
| `GET /api/case-studies/{id}/chart` | Versioned adjusted bars and annotations |
| `GET /api/case-studies/facets` | Available stocks, patterns, timeframes, and regimes |

Add administrator-only pipeline endpoints:

| Method and path | Purpose |
| --- | --- |
| `POST /api/admin/case-study-runs` | Start an asynchronous build |
| `GET /api/admin/case-study-runs/{id}` | Poll status and aggregate progress |
| `GET /api/admin/case-study-runs/{id}/items` | Paginated per-security progress |
| `POST /api/admin/case-study-runs/{id}/resume` | Resume unfinished work |

The list API should support stock/ISIN, sector, pattern type, variant,
timeframe, direction, detection period, market regime, and minimum setup score.

## 7. User interface

Add these protected routes:

```text
/case-studies
/case-studies/:caseStudyId
```

### Case-study catalog

Provide:

- symbol/company search;
- pattern family and exact pattern-type filters;
- daily, weekly, and monthly timeframe filters;
- direction, sector, market-regime, and horizon-completeness filters;
- server sorting and cursor pagination;
- result cards containing detection date, entry anchor, and 3M/6M/1Y stock
  performance.

Keep all shareable filter state in the URL.

### Case-study detail

Present the case in this order:

1. **Annotated chart:** adjusted price, pattern geometry, detection, entry
   anchor, reference levels, and completed horizon markers.
2. **Why it qualified:** exact point-in-time geometry, measurements, scores,
   supporting signals, and cautions.
3. **Forward performance:** performance to date followed by completed or
   pending 3M, 6M, and 1Y windows.
4. **Interpretation:** evidence that worked, evidence that failed, and missing
   inputs, generated from stable server rules rather than free-form claims.
5. **Lineage:** data-as-of date and all calculation versions.

Link pattern detail pages to comparable historical cases of the same pattern
type. Link a case study back to its security fingerprint and pattern evidence.

## 8. Testing and validation

### Unit tests

- next-session entry and no same-close execution;
- holidays and missing sessions;
- exact 63/126/252-session observations and forward-return formulas;
- maximum advance and maximum drawdown calculations;
- incomplete future history;
- deterministic representative-case selection.

### Repository and integration tests

- idempotent migrations and upserts;
- immutable completed case evidence;
- replay candidate to positional result to API response;
- adjustment-version changes trigger the required rebuild;
- failure isolation and resume behavior;
- server-side filters, sorting, and pagination.

### Golden cases

Maintain reviewed cases covering:

- positive, median, and negative forward-return cases;
- incomplete outcome history;
- at least one validated example for every initially supported primary pattern;
- daily, weekly, and monthly examples where supported.

Manually reconcile the entry anchor and every completed horizon for each golden
case.

### Client verification

- loading, refreshing, empty, stale, partial, error, and unauthorized states;
- chart and tabular alternatives agree with persisted facts;
- keyboard access and visible focus;
- no horizontal overflow at 320px, 390px, tablet, and desktop widths;
- setup score remains visually separate from historical outcome.

## 9. Delivery phases

### Phase 1: Positional-performance kernel

- Correct the next-session entry assumption.
- Implement 63/126/252-session calculations and tests.
- Add partial-history and completeness contracts.

### Phase 2: Persistence and pipeline

- Add case-study migrations and repositories.
- Implement the separate asynchronous Case Study Build activity.
- Add resume, per-security status, and structured failure reporting.

### Phase 3: APIs

- Add catalog, detail, chart, facets, and administrator run endpoints.
- Freeze sanitized API fixtures.

### Phase 4: UI

- Add the catalog and case-study detail routes.
- Build the annotated chart, entry rationale, forward performance, and lineage
  presentation.
- Add links from pattern detail pages.

### Phase 5: Initial reviewed catalog

- Run the build over a bounded historical period and representative universe.
- Review positive, median, negative, and incomplete cases.
- Publish the first catalog only after manual horizon reconciliation and
  point-in-time validation pass.

### Phase 6: Comparative research

- Compare each case against its pattern cohort and unfiltered baseline.
- Add adequate-sample historical probability only where the configured minimum
  sample requirement is satisfied.
- Add new pattern families after their detectors and fixtures are complete.

## Completion criteria

The feature is complete when:

- every published case can be reproduced from stored lineage and policy;
- detection uses no future candles or unconfirmed pivots;
- entry occurs only after the EOD signal was knowable;
- adjusted prices and effective-dated membership are used consistently;
- complete and incomplete horizons are visibly distinct;
- representative examples are selected by a deterministic forward-return policy;
- the annotated chart and forward returns agree with persisted server results;
- the pipeline is resumable and failures are visible by security;
- setup score is never presented as profit probability;
- the UI passes desktop, tablet, 390px, and 320px verification.
