# TradeLens Agent Guide

This file is the operating guide for contributors and coding agents working in
this repository. Preserve the established architecture and design language; do
not introduce a framework, dependency, storage layer, routing library, or
component system merely for convenience.

## Repository map

```
src/
  backend/                 Python HTTP API and PostgreSQL access
    auth/                  Authentication domain service, token helpers, models
    data_pipeline/         External market-data clients and ingestion jobs
    migrations/            Ordered, append-only PostgreSQL migrations
    pattern_engine/        Planned engine package; add per server plan
    repositories/          Repository implementations and migration runner
    server_http/           HTTP request/response boundary
  doc/                     Product specification and implementation plans
  frontend/                Vite + React single-page application
    src/api/               Planned fetch wrapper and domain API functions
    src/auth/              Planned browser session helpers
    src/components/        Reusable presentational/form components
    src/hooks/             Planned focused browser/data hooks
    src/pages/             Route-level page components
    src/routing/           Planned route matching and path builders
    src/utils/             Planned formatting, guards, query helpers
    src/styles.css         Shared design system and page styling
```

Keep domain logic out of HTTP handlers and React view components. The codebase
is deliberately small and explicit: add a focused file in the relevant layer
instead of creating broad abstractions.

## Canonical product documents

Read these before changing the positional-pattern product:

- `src/doc/positional_trading_pattern_engine_spec.md` is the canonical product,
  taxonomy, mathematical, scoring, and lifecycle specification.
- `src/doc/positional_trading_pattern_engine_implementation_plan.md` defines
  the server, database, data pipeline, engine, and backtesting phases.
- `src/doc/positional_trading_pattern_engine_client_implementation_plan.md`
  defines client screens, browser behavior, API wire contracts, and integration
  phases.

The specification wins if a plan conflicts with it. Update the relevant plan
and this guide when an accepted architectural decision changes. Do not silently
invent a different threshold, formula, identifier, response shape, or ownership
boundary.

## Product defaults that need not be restated

Unless a task explicitly says otherwise, assume all of the following:

- TradeLens is an end-of-day Indian-equities pattern-analysis product, not an
  intraday trading terminal or recommendation engine.
- NSE is an upstream server-side data source. Browsers never call NSE directly.
- User-facing prices, features, and patterns use corporate-action-adjusted data.
- Every displayed market result states its `dataAsOf` date. Stale or partially
  processed data remains clearly labelled and never appears live.
- Pattern detection, adjusted prices, features, scores, ranking, pagination,
  and historical outcomes are calculated by the server. The client formats and
  explains supplied values; it does not reconstruct them.
- Pattern identifiers and lifecycle values are stable machine contracts. Use
  exact specification values rather than display labels as stored values.
- Setup score ranks current evidence. It is not win probability, expected
  return, a recommendation, or a substitute for backtest outcomes.
- Historical research is point-in-time: no future candles, unconfirmed future
  pivots, current-only index membership, or survivorship-biased universe.
- Engine output is explainable and versioned. A result must retain enough
  measurements, events, and data/configuration lineage to reproduce it.
- Product APIs other than health and authentication require a valid bearer
  token.
- Desktop, tablet, 390px, and 320px layouts are part of normal completion, as
  are keyboard access and all loading/error/empty states.

## Working conventions

- Use `rg` for discovery and inspect the relevant files before changing them.
- Preserve existing user changes. Do not reset, discard, or reformat unrelated
  files.
- Use `apply_patch` for source edits.
- Run the narrowest relevant tests first, then the complete backend test suite
  and frontend build when a change crosses those boundaries.
- Do not commit generated files, logs, PID files, `node_modules`, virtual
  environments, or local `.env` files.
- Keep changes coherent and small. A new endpoint normally includes its
  service behavior, repository contract/implementation changes if needed, and
  tests in the same change.

## Backend architecture

### HTTP boundary

The backend uses Python's `ThreadingHTTPServer`; it is not Flask, FastAPI, or
Django. Routes belong in `src/backend/server_http/api.py`.

- Normalize paths using the existing `rstrip('/')` convention.
- Parse JSON with `_read_json()` and return JSON only through `_send_json()`.
- Return `400 Bad Request` for malformed payloads and business validation
  errors, `401 Unauthorized` for absent/invalid credentials, and `404 Not
  Found` for unknown routes.
- Keep handlers thin: extract request data, call a service, map the result to
  an HTTP payload, and return. Do not embed SQL or business rules in handlers.
- Maintain camelCase JSON fields for browser-facing payloads, while Python
  internals use snake_case.
- Parse and validate query parameters through focused helpers/services. Handlers
  must not load an entire market universe and paginate it in memory.
- New error responses use a stable envelope with `code`, user-safe `message`,
  optional `details`, and `requestId`. The existing `{ "error": "message" }`
  auth response remains supported until deliberately migrated.
- All market-data responses include `dataAsOf`, `generatedAt`, `engineVersion`,
  `configurationVersion`, and `isStale` where applicable.
- Use ISO `YYYY-MM-DD` market dates and UTC ISO-8601 timestamps. Send missing
  values as JSON `null`, never an empty string or fabricated zero.

### Product API surface

Treat the following as the default browser/server integration surface:

| Method and path | Purpose |
| --- | --- |
| `GET /api/overview` | Freshness, pipeline, market breadth, lifecycle counts, top setups |
| `GET /api/setups` | Filtered, server-sorted, cursor-paginated setup summaries and facets |
| `GET /api/patterns/{id}` | Complete pattern evidence, measurements, scores, and lineage |
| `GET /api/patterns/{id}/events` | Immutable lifecycle timeline |
| `GET /api/securities/search?q=...` | Authenticated symbol/company-name search returning stable ISINs |
| `GET /api/securities/{isin}/fingerprint` | Standard technical fingerprint |
| `GET /api/securities/{isin}/chart` | Bounded adjusted bars, indicators, levels, actions, and events |
| `POST /api/research/runs` | Start asynchronous historical research |
| `GET /api/research/runs/{id}` | Read research status |
| `GET /api/research/runs/{id}/results` | Read outcomes and comparison |

The detailed request/response examples live in the client integration plan.
Changing a field name, enum, unit, pagination model, or nullability is a contract
change and requires coordinated server tests, client fixtures, and consumers.

### Services and repositories

Services in `auth/` own validation, authentication, password checks, and token
creation. Repositories own persistence only.

- Define repository behavior as a `Protocol` near the service that consumes
  it. This keeps unit tests able to use lightweight fakes or the existing
  in-memory repository.
- Keep PostgreSQL queries parameterized using psycopg placeholders (`%s` or
  named parameters); never interpolate user input into SQL strings.
- Return simple dictionaries from repository methods, as the current auth
  code does. Convert to dataclasses at a service boundary when a typed result
  makes the API clearer.
- `PostgresUserRepository` applies migrations on construction. Preserve this
  initialization behavior for database-backed repository additions.
- In-memory repositories must remain behaviorally compatible with their
  PostgreSQL counterparts so the HTTP tests remain meaningful.

### Authentication and JWTs

Authentication uses a signed HS256 access token.

- Login is `POST /api/login` with `email` and `password`.
- Protected requests use `Authorization: Bearer <token>`.
- `GET /api/auth/me` is the canonical session validation endpoint.
- Keep token signing and parsing in `auth/jwt.py`, not in handlers or React.
- JWT payloads currently include subject (`sub`), email, admin state, issue
  time, and expiration. Do not put passwords, password hashes, database DSNs,
  or other secrets in a token.
- Token signing is configured with `JWT_SECRET`. Local values live only in
  `src/backend/.env`; document a non-secret placeholder in `.env.example`.
- Passwords are currently stored using SHA-256 for compatibility with the
  existing schema. Do not change that format without a migration and a
  deliberate password-transition plan. New security work should favor an
  explicit upgrade path rather than silently breaking existing accounts.

### Data pipeline

External exchange behavior is isolated in `data_pipeline/`.

- Put NSE-specific HTTP headers, cookies, endpoint retry behavior, and future
  NSE calls in `NseApiClient` rather than a collector or route handler.
- Put import orchestration and CSV validation in `NseDataCollector`.
- Keep persistence behind an explicit repository method such as
  `upsert_equities`.
- Preserve the public scheduled-job method name `DownloadEquities()` and its
  PEP-8 `download_equities()` alias when extending this collector.
- Validate downloaded schemas before persisting rows. Do not store an HTML
  error response or malformed CSV as market data.
- The backend process owns the unattended all-equities schedule. It runs an
  incremental pipeline at 19:00 Asia/Kolkata, records `SCHEDULED` as its
  trigger, and must not overlap another active run or create the same day's
  scheduled run twice. Interrupted scheduled work may retry automatically at
  most twice, preserving completed equities. Keep its time and batch size
  configurable through the documented environment variables.

### Opportunity ranking

- Detection state and opportunity ranking are separate concerns. Rank only
  active lifecycle states (`DETECTED` through `CONFIRMED`); terminal states are
  retained as evidence but excluded from best-fit ranking.
- Compare best-fit candidates within the same lifecycle state. Do not make an
  early forming structure compete directly with a triggered or confirmed one.
- `best-fit-v1` combines the persisted setup score (75%), context score (10%),
  and liquidity evidence (15%). Keep the API response explainable with peer
  rank, percentile, evidence completeness, strengths, and cautions.
- Best-fit and setup scores are ranking evidence, never probability of profit.
  Historical probability remains null until completed point-in-time backtests
  provide the configured minimum sample size.
- Full-universe reruns are incremental unless an administrator explicitly
  requests a force refresh: plan price requests from each security's stored
  maximum session, retain the configured historical floor as calculation
  context, and refresh corporate actions with a bounded correction overlap.

### Pattern-engine orchestration

`pattern_engine/runner.py` is the only layer that coordinates the complete
detector sequence. Keep individual detectors pure and point-in-time safe.

- Preserve the stage order: supporting signals, bases, breakouts, pullbacks,
  failures, scoring, lifecycle persistence, then expiry.
- Use `PatternEngineRunner.run_security`, `run_changed`, `run_universe`, or
  `replay` rather than recreating scan loops in HTTP handlers or jobs.
- Live writes for one security must use the pattern repository's
  `security_transaction()` boundary. A failure must roll back that security
  while allowing other universe targets to continue.
- Replay and dry-run modes must not write `pattern_instances` or
  `pattern_events`. Their result must retain candidate measurements, scoring
  contributions, and stage decisions.
- Persist scan-level metrics on `market_import_runs` and individual failures in
  `pattern_scan_failures`; do not reduce multi-security failures to logs alone.
- Pass bounded benchmark history into `DetectionContext` so relative-strength
  detectors remain date-aligned. Context scoring may rank candidates but must
  never change detector geometry.

### Market-data ingestion and adjustment

- Treat `isin` as the stable equity identity; symbols and company names may
  change over time.
- Keep raw source values, normalized values, and adjusted values distinguishable
  and traceable. Never overwrite raw bars with adjusted bars.
- The initial history job imports ten years for every eligible security and is
  resumable at a security/date-chunk checkpoint.
- The daily job imports only deltas plus a configurable repair window so late
  corrections and corporate actions are discovered safely.
- Imports are idempotent and use deterministic upserts. A retry must not create
  duplicate bars, actions, features, or pattern events.
- Record source, requested range, run ID, status, attempt, row counts, and error
  category. Never log exchange cookies or raw sensitive headers.
- Corporate actions are effective-dated and versioned. Confirm what NSE has
  already adjusted before applying factors; never double-adjust history.
- Recomputing an adjustment version invalidates and rebuilds affected features,
  swings, zones, patterns, and research results in dependency order.
- Scheduled-job methods remain callable by CLI and tests. Scheduling technology
  is an outer operational concern, not embedded in collectors or services.

### Pattern-engine architecture

Keep calculation stages separate and execute them in this order:

```text
normalize -> adjust -> features -> swings -> zones -> supporting detectors
-> primary bases -> breakouts -> pullbacks -> failures -> quality/maturity
-> context -> setup score -> lifecycle -> persistence/events
```

- Detectors are deterministic, configuration-driven, and side-effect free.
  They consume bars/features/context and return candidates; they do not save.
- The lifecycle service owns candidate matching, deduplication, transitions,
  expiry, and immutable event generation.
- Repository implementations own storage and transaction boundaries. Do not
  put SQL in a detector, scorer, service, job, or HTTP handler.
- Features, confirmed swings, zones, and patterns are keyed by security,
  effective/as-of date, and relevant calculation version.
- Swing pivots become usable only on their confirmation date. Breakout reference
  highs exclude the current trigger bar.
- Detection geometry remains independent of market/sector regime. Context may
  change ranking but must not change whether geometry exists.
- Store quality, maturity, context, and setup scores separately, including
  named component contributions. Normalize scores to 0-100 at their boundary.
- Do not create a new pattern instance on every scan. Update an overlapping
  active instance with a similar base/pivot and emit meaningful changes as
  immutable events.
- Terminal lifecycle states are `FAILED`, `INVALIDATED`, and `EXPIRED`. Do not
  move a terminal instance backwards.

Stable lifecycle vocabulary:

```text
DETECTED FORMING MATURE READY TRIGGERED CONFIRMED FAILED INVALIDATED EXPIRED
```

Stable V1 primary families:

```text
BASE-VCP BASE-FLAT BASE-52WH BRK-RANGE BRK-52WH BRK-ATH BRK-MULTIY
PB-BRKRET PB-EMA20 PB-SMA50
```

Supporting and failure identifiers must match the canonical specification.
Variants such as `VCP-3C`, `PB-SMA50-T2`, `BRK-3Y`, and `COMP-IB2` use the
canonical type/variant split; do not create near-duplicate type names.

### Backtesting and research

- Production scans and historical replay use the same detector and scorer code.
- Advance replay one trading session at a time and expose only information known
  at that point, including confirmation dates and effective-dated membership.
- Reconstruct the eligible historical universe rather than filtering today's
  securities backward through time.
- Persist run configuration, engine/data versions, filters, entry facts, sample
  completeness, and outcomes so a result is reproducible.
- Standard outcomes include 5/10/20/40/60-session returns, MFE, MAE,
  days-to-threshold, and hit-before-loss measures from the specification.
- Do not show probability-like claims for inadequate samples. Never derive
  historical probability from setup score.

### Operations and recovery

- Run operator commands from `src/backend` through `python -m operations.cli`;
  use `python -m data_pipeline.cli` for history backfill and daily NSE sync.
- `operations.cli status` is the canonical health summary. It reports the last
  terminal run per job type, import checkpoints, open anomalies, and downstream
  adjustment/feature/pattern lag.
- Rebuild one security in dependency order through `rebuild-security`; never
  rebuild patterns against stale adjustments or features manually.
- Operational events are structured and secret-safe. Do not add authorization,
  cookies, JWTs, passwords, connection strings, or raw NSE session state to an
  event's details.
- Use `benchmark-scan` with a bounded representative universe before proposing
  a numeric dependency or performance-specific architecture change.
- Backtest resume creates a linked run for the unprocessed suffix; completed
  runs and their entries/outcomes remain immutable research evidence.

### Cross-phase tests

- Use `RELIANCE` / `INE002A01018` as the representative live NSE contract and
  cross-phase integration security. Keep the reviewed source snapshot in
  `src/backend/fixtures/nse/reliance_phase18_snapshot.json`.
- Keep ordinary tests deterministic and offline. Live NSE validation is opt-in
  through `data_pipeline.cli verify-nse-contract` or
  `TRADELENS_RUN_LIVE_NSE_TESTS=1` and must not run in the normal CI job.
- Every golden scenario needs a stable name, detection expectation, rationale,
  and expected pivot, state, measurements, and scores. Maintain inventory
  traceability in `fixtures/golden/pattern_scenarios.json`.
- Run production-volume and full-universe benchmarks as explicit release gates,
  not ordinary unit tests. Record versions, machine characteristics, row or
  security counts, runtime, throughput, and failures.

### Admin pipeline console

- `/admin/pipeline` and every `/api/admin/...` endpoint are administrator-only;
  hiding the navigation link is not an authorization boundary. Always enforce
  `is_admin` at the HTTP boundary.
- Admin-triggered full-pipeline runs execute asynchronously and persist a parent
  run plus per-security stage/status rows. A slow NSE request must never hold
  the initiating HTTP response open.
- Preserve dependency order: history and corporate actions, adjusted bars,
  features, swings/zones, then pattern detection and lifecycle persistence.
- Isolate failures by security, cap one selection at 100 equities, and expose
  progress through polling-friendly status endpoints. Never emit NSE cookies or
  authentication material in run errors.
- Universe-wide admin runs snapshot all currently eligible `EQ` securities and
  process bounded batches with limited per-security concurrency. Keep every NSE
  request start behind the shared client throttle, do not hold the rate-limit
  lock while waiting for an HTTP response, and reuse universe-wide corporate
  action responses; never create one unthrottled client per worker. Production
  worker concurrency is configured by `ADMIN_PIPELINE_WORKERS` and is bounded
  to 1-8. Persist `run_scope` plus `batch_size`. The 100-equity cap still
  applies to explicit selections, not to the deliberate Run all operation.
  Paginate per-security status; do not return the complete universe on every
  polling request.

## Database and migrations

PostgreSQL is the application database. The local Docker instance is configured
via `DATABASE_URL` in `src/backend/.env`.

- Add schema changes as a new numbered `.sql` file in
  `src/backend/migrations/`; never modify an already-applied migration.
- Migration names must sort correctly, e.g. `006_create_watchlists.sql`.
- Migrations must be idempotent where practical (`CREATE TABLE IF NOT EXISTS`,
  `ADD COLUMN IF NOT EXISTS`) because local environments may be restarted.
- Seed data must be idempotent. Use `ON CONFLICT` and never overwrite a user's
  password or privileges during a normal migration.
- Use `TIMESTAMPTZ` for timestamps and database defaults such as `NOW()` when
  the database owns creation/update time.
- Use stable natural identifiers for upserts where the data source provides
  one (for NSE equities, this is `isin`).
- Never put a live DSN or secrets in migrations, source files, tests, docs, or
  commits. The local `.env` is intentionally git-ignored.

## Frontend architecture

The frontend is Vite + React with a deliberately minimal client-side router.
Do not add React Router unless a task explicitly calls for a routing-system
change.

- `App.jsx` owns pathname state, History API navigation, protected-route
  checks, and session restoration.
- Page-level views belong in `src/frontend/src/pages/`.
- Reusable form/UI behavior belongs in `src/frontend/src/components/`.
- Keep the only low-level `fetch` call in `src/frontend/src/api/apiClient.js`.
  Put endpoint contracts in focused modules under `src/frontend/src/api/`,
  token storage in `auth/authSession.js`, and use `useApiResource.js` for
  abortable, stale-response-safe page requests. Generic presentational
  components never fetch or read session storage.
- Keep `sessionStorage` and History API ownership at the app/page boundary;
  formatting and query parsing stay in focused pure utilities.
- The access token is stored in `sessionStorage` under
  `tradelensAccessToken`. Sign-out must remove it and use
  `history.replaceState` before navigating to `/` so browser Back cannot reveal
  a previously protected screen.
- A protected page must validate its token through `/api/auth/me`; checking
  that a token merely exists is not sufficient.
- Use `fetch` against relative `/api/...` paths so Vite's development proxy
  remains effective.
- Use the automatic JSX runtime configured in `vite.config.js`. Existing files
  may import React explicitly for compatibility; preserve a file's established
  import style when editing it.

### Client routes and navigation

The normal route set is `/`, `/signup`, `/overview`, `/setups`,
`/patterns/:patternId`, `/securities/:isin`, `/research`, and
`/research/:runId` for shareable historical results.

- Preserve the small History API router. Put dynamic matching and path builders
  in `src/frontend/src/routing/routes.js`; do not add React Router by default.
- Use semantic anchors for navigation and intercept only same-origin plain
  clicks. Preserve modifier-click and open-in-new-tab behavior.
- Keep screener filters, sorting, selected as-of date, and other shareable view
  state in URL query parameters, not hidden global component state.
- Use `pushState` for ordinary navigation and `replaceState` for sign-in,
  sign-out, and authentication failure.
- Unknown routes render a not-found page. Validate dynamic IDs before calling
  the API.

### Client API and asynchronous state

- The shared API client attaches JSON headers, bearer token, query parameters,
  abort signal, and structured error mapping. Never log credentials or tokens.
- Use `URLSearchParams`; treat server cursors as opaque. Omit empty optional
  filters rather than sending ambiguous empty strings.
- Abort superseded requests and component-unmount requests. An aborted request
  is not a user-facing error, and a late response must not replace newer data.
- A server-side collection owns filtering, sorting, facets, and cursor
  pagination. Default setup page size is 25 unless measurement changes it.
- Research pages must keep setup ranking separate from observed outcomes,
  state sample adequacy, and display engine/configuration/feature/adjustment
  lineage with the point-in-time universe policy.
- Every server-backed page/region defines initial loading, refreshing, empty,
  partial, stale, unauthorized, forbidden, not-found, and retryable error
  behavior as applicable.
- On `401`, clear the session and replace navigation to login. On `403`, retain
  the session and show a permission state.
- Unknown future enum and measurement fields must not crash a page. Show the raw
  enum label and place unknown measurements in an expandable fallback section.
- Do not add a global state or query/cache library by default. Start with small
  focused hooks, `AbortController`, and page-owned state.

### Market-product presentation

- `OverviewPage` shows EOD freshness/pipeline status, market regime and breadth,
  counts by lifecycle state, top-ranked setups, and the ranking disclaimer.
- `SetupsPage` uses a server-sorted table on desktop and equivalent cards on
  mobile. Filters and pagination must remain reproducible from the URL.
- `PatternDetailPage` shows security identity, state/dates, four separate score
  categories, measurements, pivot/support/invalidation, supporting evidence,
  adjusted chart, event timeline, and lineage.
- `SecurityPage` implements the standardized technical fingerprint: trend,
  primary setup, state/maturity, compression, momentum, RS, volume, location,
  context, scores, active patterns, and recent events.
- Charts consume adjusted/downsampled server series. They may compute SVG pixel
  coordinates but no financial values. Supply a keyboard-accessible textual or
  tabular alternative and never rely on color alone.
- Format INR and Indian-number grouping with `Intl.NumberFormat('en-IN')`.
  A server field ending in `Pct` already contains percentage points: `1.7`
  displays as `1.7%`, not `170%`.

## Frontend design system

`src/frontend/src/topology.css` is the shared design-token source of truth;
`src/frontend/src/styles.css` consumes those tokens for component and page
rules. The system intentionally uses a small set of recurring visual tokens
rather than a third-party UI kit.

### Visual language

TradeLens is a dark, calm market-analysis product with warm amber accents.
Prefer restrained contrast and generous spacing over dashboards crowded with
controls.

| Token area | Established pattern | Use it for |
| --- | --- | --- |
| Canvas | near-black to brown/forest gradient with subtle radial glows | page backgrounds |
| Primary text | `#f6ecd6` / `#fff8ea` | headings and active input text |
| Muted text | `rgba(246, 236, 214, 0.58–0.8)` | descriptions, metadata, labels |
| Accent | `#ffdf84`, `#ffdc89`, `#f28d3f` | primary CTA, eyebrow text, focus state |
| Surfaces | `rgba(8–11, 10–14, 14–18, 0.42–0.78)` | cards and overlay panels |
| Borders | `rgba(255, 236, 199, 0.1–0.12)` | cards, inputs, pills |
| Radius | `1rem–1.25rem` controls/cards; `2rem` main panels; `999px` pills | all rounded UI |
| Shadows | `0 2rem 6rem rgba(0, 0, 0, 0.34)` | major elevated panels only |

### Components and interaction states

- Primary actions use the amber gradient, dark text, strong weight, and a
  restrained warm shadow (`.primary-button`).
- Secondary actions remain low-contrast dark surfaces with the standard warm
  border (`.secondary-button`).
- Inputs use the dark translucent surface and an amber focus ring; do not
  introduce bright blue browser-default focus styles.
- Cards use a warm translucent border, dark surface, and consistent corner
  radius. Avoid mixing sharp corners or opaque white cards into the app.
- Keep hover motion subtle (`translateY(-1px)` and short transitions). Do not
  add large transforms, bouncy animation, or flashing market-style effects.
- Retain semantic HTML, visible labels, keyboard-capable native controls, and
  descriptive `aria-label`s for form/page regions.
- Use one `h1` per page, a skip link in the authenticated shell, ordered heading
  levels, labelled tables, announced sort direction, and restrained live-region
  updates for result counts and errors.
- A filter drawer behaves as a dialog: labelled title, close action, Escape,
  focus containment, and focus restoration.
- Lifecycle state and score meaning must use text and shape/icon cues in
  addition to color.

### Layout and responsiveness

- Base pages use `min-height: 100vh` with `clamp()`-based outer padding.
- Desktop login/signup layouts are two columns; the existing `980px` media
  query intentionally collapses them to one column.
- At the `640px` mobile breakpoint, use the mobile spacing/radius tokens from
  `topology.css`, stack dense rows (including password controls and form
  utility rows), keep navigation wrapped and left-aligned, and reduce display
  type without reducing hierarchy.
- Mobile controls must remain comfortably touchable: preserve the shared
  `--size-control-min-block` minimum height and avoid icon-only actions without
  an accessible name.
- Keep page content inside the viewport width at 320px and 390px. Do not use
  fixed card widths, horizontal overflow, or side-by-side form controls that
  force a narrow screen to scroll sideways.
- On mobile, normal content may scroll vertically, but auth forms should use
  compact panel padding and purposeful gaps; remove decorative or duplicate
  content before squeezing labels, inputs, or actions.
- A page that is intended to be a single-screen auth flow must fit the normal
  viewport without unnecessary vertical scroll. Before finishing such work,
  inspect `scrollHeight` against `window.innerHeight`.
- Scope compact spacing changes to the relevant modifier (for example,
  `.login-shell--signup`) instead of shrinking shared login styles and
  accidentally damaging another route.
- Overview pages may have more room, but should maintain the same heading,
  card, border, typography, and accent rules as auth pages.
- Add responsive rules for newly introduced multi-column grids. The overview
  grid, for example, should collapse at the same breakpoint as other layouts.

## Verification

Run commands from the indicated working directory.

```powershell
# Backend tests (repository root)
py -3.11 -m unittest discover -s src\backend -p "test*.py" -v

# Frontend production build
cd src\frontend
npm run build

# Restart local services (repository root; requires ownership of port listeners)
.\restart-services.ps1
```

When frontend tests are introduced, keep a stable `npm test` script and run it
before `npm run build`. Prefer unit tests for route/query/formatting/API helpers,
component tests for interactions and async states, and checked-in sanitized API
fixtures for contracts. Do not put tokens or large production payloads in
fixtures.

For UI work, verify the relevant route after Vite has reloaded and confirm:

- no browser console errors;
- authentication requests return the expected status;
- protected routes redirect after token removal or expiry;
- sign-out does not allow Back to reveal protected content;
- the target auth page has no unintended vertical scroll at the normal desktop
  viewport and still works at 390px-wide and 320px-wide mobile breakpoints;
- no route has horizontal overflow at the tested mobile widths;
- setup filters and sort survive refresh, Back/Forward, and copied URLs;
- stale/partial data is visibly labelled with its market date;
- desktop tables and mobile cards expose the same decision-critical fields;
- charts agree with server levels/measurements and have a non-visual fallback.

`restart-services.ps1` is responsible for replacing services on ports 5004 and
9004. If Windows denies stopping a listener owned by another account, report
the exact PID and require the user to run the script from an Administrator
PowerShell; do not silently claim the restart succeeded.

## Completion checklist

Before handing off a change, confirm the following as applicable:

- Architecture boundaries remain intact (handler -> service -> repository).
- Market processing follows the canonical stage order and detectors remain
  pure/configuration-driven.
- New database schema is an append-only migration with safe repeat behavior.
- Secrets remain in local environment files and are absent from Git-tracked
  files and response logs.
- New API behavior has an automated backend test, including authorization
  failures where relevant.
- Changed API contracts update server tests, client contract fixtures, and all
  consuming pages together.
- Frontend code builds successfully and the relevant route is visually checked.
- Server-backed UI includes applicable loading, refreshing, empty, stale,
  partial, authorization, not-found, and retry states.
- Visual additions use the established warm-dark tokens, radii, spacing, and
  responsive breakpoints.
- Pattern results preserve measurements, separate scores, events, and version
  lineage; setup score is not presented as probability.
- Local services are either verified healthy or any port/permission blocker is
  stated plainly.
