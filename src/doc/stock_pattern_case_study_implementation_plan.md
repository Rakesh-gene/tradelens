# Stock Pattern Case Study Implementation Plan

## Purpose

TradeLens should provide reproducible stock case studies that explain how a
pattern was identified using information available at the time and show the
hypothetical profit or loss from a clearly defined trade policy.

Case studies are historical research evidence. They are not recommendations,
probability claims, or proof that a current setup will produce the same result.
They must follow the point-in-time, adjusted-price, lifecycle, and versioning
rules in `positional_trading_pattern_engine_spec.md`.

## Existing foundation

The repository already provides:

- point-in-time detector replay using the production detector and scorer path;
- `backtest_runs`, `backtest_entries`, and `backtest_outcomes` persistence;
- authenticated research run and result APIs;
- 5, 10, 20, 40, and 60-session returns;
- maximum favorable excursion (MFE) and maximum adverse excursion (MAE);
- days-to-threshold and hit-before-loss outcomes;
- engine, configuration, feature, adjustment, and universe-policy lineage.

The case-study feature should reuse these capabilities. It needs a realistic,
versioned trade policy, deterministic case selection, case-study persistence,
a separate pipeline activity, and dedicated user-facing screens.

## 1. Versioned trade policy

Introduce a policy such as `swing-trade-v1`. Every case study must store the
policy version and all inputs used by the simulation.

### Entry

- The pattern must reach `TRIGGERED` or `CONFIRMED`.
- An end-of-day signal becomes known only after the detection-session close.
- The default hypothetical entry is the next trading session's adjusted open.
- If the next session opens beyond the configured maximum entry extension, the
  trade is skipped and records `ENTRY_GAP_TOO_LARGE`.
- A pattern without a valid invalidation price is not eligible for the default
  risk-managed simulation.

The existing research implementation currently uses the trigger-day close as
entry. Correct that assumption before publishing case studies. Keep fixed
horizon research returns available as separate statistical outcomes.

### Position size

Use normalized assumptions so cases remain comparable:

```text
Reference capital = INR 100,000
Risk budget        = 1% of reference capital
Risk per share     = Entry price - Stop price
Quantity           = floor(Risk budget / Risk per share)
```

Do not allow fractional shares. If the risk per share is non-positive or the
position cannot be purchased with the reference capital, record the case as
not tradable under the selected policy.

### Stop, target, and exit

- Initial stop: the pattern's persisted invalidation price known at entry.
- Default target: `2R`, where `R` is the initial per-share risk.
- Time exit: adjusted close after 20 trading sessions if neither stop nor
  target was reached.
- Gap through stop or target: use the next session's opening price.
- Stop and target touched in the same daily candle: use the conservative
  stop-first assumption and label the result `AMBIGUOUS_INTRADAY_SEQUENCE`.
- Do not introduce trailing stops until a separate policy defines their exact
  point-in-time rules.

### Profit and loss

Store and display:

```text
Gross P/L       = (Exit price - Entry price) * Quantity
Gross return %  = (Exit price / Entry price - 1) * 100
Net P/L         = Gross P/L - configured costs
Net return %    = Net P/L / deployed capital * 100
R multiple      = Net P/L / initial risk amount
```

Brokerage, taxes, fees, and slippage must be configurable and versioned. Do not
hard-code a claim that a cost model represents a user's actual broker charges.

## 2. Case-study selection policy

Case selection must be deterministic and must not cherry-pick only profitable
examples.

Build a stratified catalog across:

- pattern type and variant;
- daily, weekly, and monthly timeframes;
- bullish and bearish directions;
- strong, neutral, and weak market regimes;
- strong and weak sector context;
- profitable, losing, stopped, timed-out, skipped, ambiguous, and incomplete
  outcomes.

For each supported pattern and timeframe combination, select representative
cases using a stable rule such as:

1. highest net R multiple;
2. median net R multiple;
3. lowest net R multiple;
4. first stopped case;
5. first incomplete or ambiguous case when one exists.

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
4. simulate the configured trade policy;
5. calculate P/L, R multiple, MFE, MAE, and fixed-horizon outcomes;
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
- trade-policy and selection-policy versions;
- progress counts, timing, failure summary, and initiating user;
- point-in-time and survivorship-bias policies.

### `case_studies`

Store:

- stable case-study ID;
- source backtest run and entry IDs;
- ISIN and historical symbol/company identity;
- pattern type, variant, group, direction, timeframe, and lifecycle state;
- pattern start, detection, trigger, confirmation, entry, and exit dates;
- entry, stop, target, exit, support, and invalidation prices;
- pattern measurements and supporting evidence;
- market, sector, relative-strength, and liquidity context;
- exit reason, completeness, ambiguity, and review status;
- complete calculation lineage.

### `case_study_trade_results`

Store:

- quantity, deployed capital, and initial risk;
- gross P/L, costs, net P/L, and net return percentage;
- gross and net R multiples;
- MFE and MAE;
- fixed-horizon returns and completeness;
- target/stop touch dates and the applied same-session policy.

Do not duplicate adjusted candles. Retrieve them through the existing market
data repository using the case's adjustment version.

## 5. Service boundaries

Add focused modules rather than placing simulation logic in HTTP handlers or
React components:

```text
src/backend/pattern_engine/trade_simulation.py
src/backend/pattern_engine/case_study_selection.py
src/backend/pattern_engine/case_study_service.py
src/backend/repositories/case_studies.py
src/backend/operations/case_study_pipeline.py
```

- `trade_simulation.py` owns deterministic entry, position sizing, stop,
  target, exit, gap, cost, and P/L calculations.
- `case_study_selection.py` owns stratification and deterministic selection.
- `case_study_service.py` owns queries and browser-facing contracts.
- repositories own SQL and transactions.
- the pipeline owns orchestration, progress, retry, and failure isolation.
- React renders server-supplied facts and does not recalculate P/L.

## 6. API surface

Add authenticated product endpoints:

| Method and path | Purpose |
| --- | --- |
| `GET /api/case-studies` | Filtered, sorted, cursor-paginated case summaries |
| `GET /api/case-studies/{id}` | Complete detection, trade, outcome, and lineage evidence |
| `GET /api/case-studies/{id}/chart` | Versioned adjusted bars and annotations |
| `GET /api/case-studies/facets` | Available stocks, patterns, timeframes, outcomes, and regimes |

Add administrator-only pipeline endpoints:

| Method and path | Purpose |
| --- | --- |
| `POST /api/admin/case-study-runs` | Start an asynchronous build |
| `GET /api/admin/case-study-runs/{id}` | Poll status and aggregate progress |
| `GET /api/admin/case-study-runs/{id}/items` | Paginated per-security progress |
| `POST /api/admin/case-study-runs/{id}/resume` | Resume unfinished work |

The list API should support stock/ISIN, sector, pattern type, variant,
timeframe, direction, detection period, exit reason, profitable/loss outcome,
market regime, and minimum setup score.

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
- direction, sector, market-regime, and outcome filters;
- profitable, losing, stopped, target-hit, time-exit, skipped, ambiguous, and
  incomplete result filters;
- server sorting and cursor pagination;
- result cards containing detection date, entry, exit, net P/L, return, R
  multiple, and exit reason.

Keep all shareable filter state in the URL.

### Case-study detail

Present the case in this order:

1. **What was known:** the exact evidence available on the detection date.
2. **Why it qualified:** geometry, measurements, scores, and supporting signals.
3. **Trade assumptions:** policy version, entry, stop, target, capital, risk,
   quantity, costs, and ambiguity policy.
4. **Annotated chart:** pattern geometry, detection, trigger, entry, stop,
   target, exit, and relevant lifecycle events.
5. **Outcome:** gross and net P/L, percentage return, R multiple, MFE, MAE,
   duration, and exit reason.
6. **Interpretation:** evidence that worked, evidence that failed, and missing
   inputs, generated from stable server rules rather than free-form claims.
7. **Lineage:** data-as-of date and all calculation versions.

Link pattern detail pages to comparable historical cases of the same pattern
type. Link a case study back to its security fingerprint and pattern evidence.

## 8. Testing and validation

### Unit tests

- next-session entry and no same-close execution;
- position sizing and insufficient-capital behavior;
- ordinary, gap, target, stop, and time exits;
- stop and target touched in the same candle;
- holidays and missing sessions;
- costs, net P/L, percentage return, and R-multiple formulas;
- incomplete future history;
- deterministic representative-case selection.

### Repository and integration tests

- idempotent migrations and upserts;
- immutable completed case evidence;
- replay candidate to trade result to API response;
- adjustment-version changes trigger the required rebuild;
- failure isolation and resume behavior;
- server-side filters, sorting, and pagination.

### Golden cases

Maintain reviewed cases covering:

- a profitable target exit;
- a stop-loss exit;
- a gap through the stop;
- a time exit;
- a same-session stop/target ambiguity;
- incomplete outcome history;
- at least one validated example for every initially supported primary pattern;
- daily, weekly, and monthly examples where supported.

Manually reconcile entry, exit, quantity, costs, and P/L for each golden case.

### Client verification

- loading, refreshing, empty, stale, partial, error, and unauthorized states;
- chart and tabular alternatives agree with persisted facts;
- keyboard access and visible focus;
- no horizontal overflow at 320px, 390px, tablet, and desktop widths;
- setup score remains visually separate from historical outcome.

## 9. Delivery phases

### Phase 1: Simulation kernel

- Correct the next-session entry assumption.
- Implement `swing-trade-v1` and calculation tests.
- Add cost, ambiguity, and completeness contracts.

### Phase 2: Persistence and pipeline

- Add case-study migrations and repositories.
- Implement the separate asynchronous Case Study Build activity.
- Add resume, per-security status, and structured failure reporting.

### Phase 3: APIs

- Add catalog, detail, chart, facets, and administrator run endpoints.
- Freeze sanitized API fixtures.

### Phase 4: UI

- Add the catalog and case-study detail routes.
- Build the annotated chart, trade summary, evidence explanation, and lineage
  presentation.
- Add links from pattern detail pages.

### Phase 5: Initial reviewed catalog

- Run the build over a bounded historical period and representative universe.
- Review winning, losing, skipped, ambiguous, and incomplete cases.
- Publish the first catalog only after manual P/L reconciliation and
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
- all costs and ambiguous assumptions are visible;
- profitable and losing examples are selected by a deterministic policy;
- the annotated chart and calculated P/L agree with persisted server results;
- the pipeline is resumable and failures are visible by security;
- setup score is never presented as profit probability;
- the UI passes desktop, tablet, 390px, and 320px verification.
