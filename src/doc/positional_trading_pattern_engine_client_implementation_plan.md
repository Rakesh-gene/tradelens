# Positional Trading Pattern Engine — Client and API Integration Plan

- **Plan version:** 1.0
- **Source specification:** `src/doc/positional_trading_pattern_engine_spec.md`
- **Companion server plan:**
  `src/doc/positional_trading_pattern_engine_implementation_plan.md`
- **Target client:** `src/frontend`, React 19 and Vite 6
- **Design system:** `src/frontend/src/topology.css`

## 1. Purpose

This document defines the client-side implementation of the positional trading
pattern engine. It describes the pages, components, state, API contracts,
authentication behavior, error handling, responsive layouts, accessibility,
tests, and delivery order needed to turn the engine output into a usable
TradeLens product.

The client does not detect patterns, calculate scores, infer lifecycle state,
or reconstruct adjusted prices. Those are server responsibilities. The client
requests versioned results, renders the evidence supplied by the server, and
lets users search, filter, inspect, and compare those results.

## 2. Existing frontend baseline

The current application has:

- `App.jsx` with a small History API router;
- `/` login, `/signup`, and protected `/overview` routes;
- JWT storage in `sessionStorage` under `tradelensAccessToken`;
- session validation through `GET /api/auth/me`;
- relative `/api/...` requests proxied by Vite to `127.0.0.1:9004`;
- reusable `AuthForm` and a temporary `OverviewPage`;
- shared design tokens in `topology.css` and rules in `styles.css`;
- no React Router, query library, global state library, chart library, or test
  runner.

Preserve these decisions initially. Add a dependency only when a measured need
cannot be met cleanly with React and browser APIs.

## 3. Client responsibilities and boundaries

### Client owns

- navigation and protected-route behavior;
- session storage and bearer-token attachment;
- URL-backed filters and selected dates;
- loading, empty, stale, partial, and error states;
- responsive rendering of overview, setup lists, fingerprints, charts, and
  timelines;
- formatting server values for people without changing their meaning;
- accessible interaction and keyboard behavior;
- request cancellation and prevention of stale-response races.

### Server owns

- the eligible universe and liquidity policy;
- adjusted OHLCV and corporate-action processing;
- every feature, pattern measurement, lifecycle transition, and score;
- market and sector context calculations;
- ranking, pagination, filter validation, and historical probability;
- point-in-time correctness and data/configuration lineage.

### Forbidden client behavior

- Do not recalculate pattern state from chart bars.
- Do not recalculate setup score from displayed components.
- Do not treat a missing field as zero unless the API contract says so.
- Do not sort a paginated result set locally and imply that it is a global
  ranking.
- Do not call NSE directly from the browser.
- Do not expose source cookies, database identifiers, internal exceptions, or
  JWT contents in the interface.
- Do not label setup score as probability or expected return.

## 4. Target navigation model

Keep routing in `App.jsx`, but move route parsing to a focused helper once
dynamic routes are added.

| Route | Access | Page | Purpose |
|---|---|---|---|
| `/` | Public | `LoginPage` | Authenticate |
| `/signup` | Public | `SignupPage` | Create an account |
| `/overview` | Protected | `OverviewPage` | Market and opportunity summary |
| `/setups` | Protected | `SetupsPage` | Filtered, paginated opportunity list |
| `/patterns/:patternId` | Protected | `PatternDetailPage` | Pattern evidence and timeline |
| `/securities/:isin` | Protected | `SecurityPage` | Complete technical fingerprint |
| `/research` | Protected, later | `ResearchPage` | Historical pattern outcome analysis |

Unknown public or protected paths render `NotFoundPage`. When the path is
protected and the session is missing or invalid, replace history with `/`.

### Route matching

Create `src/frontend/src/routing/routes.js` with:

```js
export function matchRoute(pathname) {}
export function buildPatternPath(patternId) {}
export function buildSecurityPath(isin) {}
export function isProtectedRoute(route) {}
```

`matchRoute()` returns a stable route object such as:

```js
{
  name: 'pattern-detail',
  params: { patternId: '7a...' },
  protected: true,
}
```

Decode dynamic segments safely. An invalid UUID or ISIN should reach a local
not-found state without sending a malformed request.

### Navigation behavior

- Use `pushState` for normal navigation.
- Use `replaceState` after sign-in, sign-out, and authentication failure.
- Listen to `popstate` once in `App.jsx`.
- Provide a shared `navigate(path, { replace })` callback.
- Use semantic anchors for links so open-in-new-tab and copied URLs work.
- Intercept same-origin left clicks only; do not break modifier keys.
- Restore filter state from the URL when users use Back or Forward.
- Never render protected page content while session validation is pending.

## 5. Proposed frontend file structure

```text
src/frontend/src/
  api/
    apiClient.js
    authApi.js
    marketApi.js
    patternApi.js
    researchApi.js
    securityApi.js
  auth/
    authSession.js
  components/
    AppShell.jsx
    AuthForm.jsx
    Breadcrumbs.jsx
    DataFreshness.jsx
    EmptyState.jsx
    ErrorState.jsx
    FilterDrawer.jsx
    LifecycleBadge.jsx
    LoadingSkeleton.jsx
    MarketRegimeCard.jsx
    MetricCard.jsx
    PaginationControls.jsx
    PatternCard.jsx
    PatternChart.jsx
    PatternFilters.jsx
    PatternTimeline.jsx
    ScoreBreakdown.jsx
    ScoreGauge.jsx
    SecuritySearch.jsx
    SetupTable.jsx
    SupportingPatternList.jsx
    TechnicalFingerprint.jsx
  hooks/
    useApiResource.js
    useDebouncedValue.js
    useDocumentTitle.js
    useMediaQuery.js
    useSession.js
    useUrlFilters.js
  pages/
    LoginPage.jsx
    SignupPage.jsx
    OverviewPage.jsx
    SetupsPage.jsx
    PatternDetailPage.jsx
    SecurityPage.jsx
    ResearchPage.jsx
    NotFoundPage.jsx
  routing/
    routes.js
  utils/
    formatters.js
    guards.js
    queryString.js
  App.jsx
  main.jsx
  topology.css
  styles.css
```

Do not create a generic component framework. Each shared component must have at
least two real consumers or represent a stable product primitive such as a
lifecycle badge or score breakdown.

## 6. HTTP client layer

Create `api/apiClient.js` as the only low-level wrapper around `fetch`.

```js
export class ApiError extends Error {
  constructor(message, { status, code, details, requestId } = {}) {}
}

export async function apiRequest(path, options = {}) {}
```

Supported options:

```js
{
  method: 'GET',
  body: undefined,
  token: undefined,
  signal: undefined,
  query: undefined,
}
```

Implementation rules:

1. Require a relative path beginning with `/api/`.
2. Encode query values using `URLSearchParams`; omit `undefined`, `null`, and
   empty filter values.
3. Add `Accept: application/json`.
4. Add `Content-Type: application/json` only when a JSON body exists.
5. Add `Authorization: Bearer <token>` only for authenticated calls.
6. Serialize the body once.
7. Pass `AbortSignal` to `fetch`.
8. Parse JSON only when the content type is JSON.
9. Convert non-2xx responses into `ApiError`.
10. Preserve `status`, stable server `code`, field `details`, and `requestId`.
11. Map an unexpected non-JSON response to `INVALID_RESPONSE`.
12. Do not log the bearer token or request body.

The wrapper must not automatically retry mutations. A single GET retry is
acceptable only for transient network failure and only after cancellation is
distinguished from failure. Rate-limit responses should respect a future
`Retry-After` header rather than tight-looping.

### Standard server error envelope

All new APIs should return:

```json
{
  "error": {
    "code": "INVALID_FILTER",
    "message": "The state filter is not supported.",
    "details": { "field": "state" },
    "requestId": "req_..."
  }
}
```

During transition, `apiRequest()` should also accept the existing auth shape
`{ "error": "message" }`. New endpoints should use the structured envelope.

### HTTP behavior matrix

| Status | Client behavior |
|---|---|
| `200` | Render returned data |
| `201` | Complete registration and continue to sign-in or authenticated route |
| `400` | Show filter/form error; preserve user input |
| `401` | Clear session, replace route with `/`, show session-expired notice |
| `403` | Render permission state without signing out |
| `404` | Render resource-not-found page |
| `409` | Show conflict message, such as an existing account |
| `422` | Attach field errors when supplied |
| `429` | Show temporary rate-limit state and retry timing |
| `500+` | Show recoverable server error with retry action |

## 7. Authentication integration

### Existing APIs

#### `POST /api/login`

Request:

```json
{ "email": "user@example.com", "password": "secret" }
```

Expected response:

```json
{
  "accessToken": "...",
  "user": { "id": "...", "email": "user@example.com", "isAdmin": false }
}
```

This is the current wire contract. If the backend later adds `tokenType` or
`expiresIn`, treat them as additive optional fields and keep session validation
through `/api/auth/me` authoritative.

#### `POST /api/register`

Request includes `email`, `password`, and `confirmPassword`. The client performs
basic completeness/match checks for fast feedback; the server remains the
authority for all validation.

#### `GET /api/auth/me`

Expected response:

```json
{
  "user": { "id": "...", "email": "user@example.com", "isAdmin": false }
}
```

### Session module

Create `auth/authSession.js`:

```js
export const ACCESS_TOKEN_KEY = 'tradelensAccessToken'
export function readAccessToken() {}
export function writeAccessToken(token) {}
export function clearAccessToken() {}
```

Create `api/authApi.js`:

```js
export function login(credentials, options) {}
export function register(registration, options) {}
export function getCurrentUser(token, options) {}
```

`App.jsx` remains the owner of the authenticated user. `useSession()` may
encapsulate validation later, but it must retain these guarantees:

- validate the token with `/api/auth/me` before displaying any protected page;
- clear an invalid/expired token;
- use history replacement on sign-out and failed validation;
- abort validation when the route changes or the component unmounts;
- ignore a superseded validation response;
- provide `checking`, `authenticated`, and `anonymous` states;
- do not decode the JWT to decide authorization.

Registration V1 should redirect to `/` with a one-time “Account created”
message after success. If the server later returns a JWT on registration, use
the normal authenticated callback and document that contract change.

## 8. API contract conventions

All dates are ISO `YYYY-MM-DD`. All timestamps are UTC ISO-8601 strings ending
in `Z`. Price and score fields are JSON numbers. Missing data is `null`, not an
empty string or fabricated zero.

Every market-data response should include:

```json
{
  "dataAsOf": "2026-09-04",
  "generatedAt": "2026-09-04T13:15:00Z",
  "engineVersion": "1.0.0",
  "configurationVersion": "2026-09-01",
  "isStale": false
}
```

The client displays `dataAsOf` prominently because this is an end-of-day
product. `generatedAt` is secondary diagnostic metadata. If `isStale` is true,
show a non-blocking stale-data banner; never silently make yesterday's data
look live.

Enums use the specification identifiers exactly, including `BASE-VCP`,
`VCP-3C`, `READY`, and `FAIL-BRK`. Unknown future enum values render as their
raw label and must not crash the page.

## 9. Endpoint integration catalogue

### Available now

| Method and path | Auth | Client consumer |
|---|---|---|
| `GET /api/health` | No | Development diagnostics only |
| `POST /api/register` | No | `SignupPage` |
| `POST /api/login` | No | `LoginPage` |
| `GET /api/auth/me` | Bearer | `App.jsx` session restoration |

### Required for product V1

| Method and path | Client consumer | Server-plan relationship |
|---|---|---|
| `GET /api/overview` | `OverviewPage` | Already planned |
| `GET /api/setups` | `SetupsPage` | Already planned |
| `GET /api/patterns/{id}` | `PatternDetailPage` | Already planned |
| `GET /api/patterns/{id}/events` | Timeline | Already planned |
| `GET /api/securities/{isin}/fingerprint` | `SecurityPage` | Already planned |
| `GET /api/securities` | Header search | Explicit client integration addition |
| `GET /api/securities/{isin}/chart` | Chart on security/pattern pages | Explicit client integration addition |

All product V1 endpoints require a bearer token. The browser calls only the
TradeLens API. The TradeLens backend is solely responsible for NSE integration.

### Later research endpoints

| Method and path | Client consumer |
|---|---|
| `POST /api/research/runs` | Start a research query/backtest |
| `GET /api/research/runs/{id}` | Poll run status |
| `GET /api/research/runs/{id}/results` | Outcome tables and comparisons |
| `DELETE /api/research/runs/{id}` | Cancel a running job, if supported |

## 10. Overview API and page

### Request

```http
GET /api/overview?asOf=2026-09-04&top=10
Authorization: Bearer <token>
```

`asOf` is optional and defaults to the latest completed engine date. `top` is
bounded by the server.

### Response shape

```json
{
  "dataAsOf": "2026-09-04",
  "generatedAt": "2026-09-04T13:15:00Z",
  "engineVersion": "1.0.0",
  "configurationVersion": "2026-09-01",
  "isStale": false,
  "pipeline": {
    "status": "COMPLETE",
    "lastSuccessfulRunAt": "2026-09-04T13:10:00Z",
    "securitiesScanned": 1890,
    "failedSecurities": 0
  },
  "market": {
    "regimeScore": 78.0,
    "label": "CONSTRUCTIVE",
    "benchmark": "NIFTY500",
    "aboveEma20Pct": 63.2,
    "aboveSma50Pct": 58.4,
    "aboveSma200Pct": 54.7,
    "new52WeekHighs": 37,
    "new52WeekLows": 8,
    "breakouts": 21,
    "failedBreakouts": 4
  },
  "countsByState": {
    "READY": 48,
    "TRIGGERED": 12,
    "CONFIRMED": 9,
    "FAILED": 4
  },
  "topSetups": []
}
```

`topSetups` uses the compact setup summary contract from the setups endpoint.

### Page composition

Replace the placeholder `OverviewPage` with:

1. `AppShell` header containing brand, primary navigation, security search, and
   user/sign-out controls.
2. `DataFreshness` showing the market date and import state.
3. Market regime card with the score, label, benchmark, and breadth evidence.
4. Lifecycle count cards linking to prefiltered `/setups?state=READY`, etc.
5. “Highest-ranked setups” list with a link to the complete screener.
6. A concise disclosure: setup score is ranking evidence, not outcome
   probability or financial advice.

### Page states

- Initial load: render layout-preserving skeletons.
- Empty: explain that the latest scan found no eligible setups.
- Partial pipeline: show available prior complete date and warning.
- Stale: keep content visible under a stale-data banner.
- Error: show retry and retain the application shell.

## 11. Setups list API and page

### Request

```http
GET /api/setups?asOf=2026-09-04&pageSize=25&state=READY&patternType=BASE-VCP&minSetupScore=80&sort=setupScore&direction=desc
```

Supported query parameters:

| Parameter | Values |
|---|---|
| `asOf` | ISO date |
| `cursor` | Opaque server cursor |
| `pageSize` | 10–100, default 25 |
| `patternClass` | `TREND`, `BASE`, `BREAKOUT`, `PULLBACK`, `COMPRESSION`, `MOMENTUM`, `FAILURE` |
| `patternType` | Stable specification identifier |
| `variant` | Stable variant identifier |
| `state` | Lifecycle enum; repeatable or comma-separated per final server contract |
| `sector` | Stable sector identifier |
| `minSetupScore`, `maxSetupScore` | 0–100 |
| `minRs6m` | 0–100 percentile |
| `minLiquidityScore` | 0–100 |
| `sort` | `setupScore`, `qualityScore`, `maturityScore`, `detectedDate`, `distanceToPivotPct` |
| `direction` | `asc` or `desc` |

Choose one documented encoding for multi-value filters and use it everywhere.
The recommended V1 encoding repeats the key, for example
`state=READY&state=TRIGGERED`.

### Response

```json
{
  "dataAsOf": "2026-09-04",
  "items": [
    {
      "patternInstanceId": "...",
      "security": {
        "isin": "INE...",
        "symbol": "EXAMPLE",
        "name": "Example Limited",
        "sectorId": "financial-services",
        "sectorName": "Financial Services"
      },
      "patternClass": "BASE",
      "patternType": "BASE-VCP",
      "variant": "VCP-3C",
      "state": "READY",
      "detectedDate": "2026-08-18",
      "lastUpdatedDate": "2026-09-04",
      "qualityScore": 92.0,
      "maturityScore": 88.0,
      "contextScore": 90.0,
      "setupScore": 89.0,
      "pivotPrice": 500.0,
      "lastClose": 491.5,
      "distanceToPivotPct": -1.7,
      "supportingPatterns": ["TREND-S2", "COMP-ATR", "VOL-DRY"]
    }
  ],
  "nextCursor": "opaque-or-null",
  "facets": {
    "states": [{ "value": "READY", "count": 48 }],
    "patternTypes": [{ "value": "BASE-VCP", "count": 21 }],
    "sectors": [{ "value": "financial-services", "label": "Financial Services", "count": 12 }]
  }
}
```

### URL-backed filter state

`useUrlFilters()` parses and validates filters from `window.location.search`.
Changing a filter:

1. clears the cursor;
2. updates the URL;
3. aborts the previous request;
4. issues the new request;
5. preserves old results in a visibly refreshing state until the response
   arrives, unless the as-of date changed.

Unknown query parameters are ignored. Invalid known values are removed and a
small correction notice is shown. Copying the URL must reproduce the same
filter set.

### Desktop and mobile layouts

Desktop uses a compact sortable table with columns for security, pattern,
state, setup score, quality, maturity, pivot distance, sector, and as-of date.
Mobile renders the same data as `PatternCard` items; do not force a wide table
into horizontal scrolling for primary use.

Filters are inline on large screens and a modal/drawer on small screens. The
drawer needs a label, close button, Escape handling, focus containment, focus
restoration, Apply, and Clear actions.

Sorting always requests the server. Pagination uses the opaque cursor and
disables controls while a request is pending.

## 12. Pattern detail APIs and page

### Pattern request

```http
GET /api/patterns/{patternInstanceId}
```

Response follows the standard pattern instance schema from the specification
and adds security identity, formatted explanation inputs, and lineage:

```json
{
  "pattern": {
    "patternInstanceId": "...",
    "security": { "isin": "INE...", "symbol": "EXAMPLE", "name": "Example Limited" },
    "patternClass": "BASE",
    "patternType": "BASE-VCP",
    "variant": "VCP-3C",
    "startDate": "2026-07-15",
    "detectedDate": "2026-08-18",
    "lastUpdatedDate": "2026-09-04",
    "state": "READY",
    "qualityScore": 92.0,
    "maturityScore": 88.0,
    "contextScore": 90.0,
    "setupScore": 89.0,
    "pivotPrice": 500.0,
    "supportPrice": 462.0,
    "invalidationPrice": 457.0,
    "measurements": {},
    "scoreComponents": [],
    "supportingPatterns": [],
    "lineage": {
      "engineVersion": "1.0.0",
      "configurationVersion": "2026-09-01",
      "adjustmentVersion": "..."
    }
  }
}
```

### Events request

```http
GET /api/patterns/{patternInstanceId}/events?cursor=...&pageSize=50
```

Each event contains `eventId`, `eventType`, `effectiveDate`, `recordedAt`,
`previousState`, `newState`, and a typed `changes` object. Render `effectiveDate`
as the main timeline date. Put `recordedAt` and raw changes in expandable
technical details.

### Page composition

- Breadcrumbs: Setups → symbol → pattern variant.
- Security identity and latest close.
- Lifecycle badge and detected/updated dates.
- Separate quality, maturity, context, and setup score cards.
- Evidence-first score breakdown; never display only the composite.
- Pattern geometry measurements appropriate to the pattern type.
- Pivot, support, invalidation, and current-distance values.
- Supporting signals grouped by trend, compression, momentum, and volume.
- Adjusted chart with pattern window, pivot/support lines, and event markers.
- Immutable technical timeline.
- Lineage section with engine/configuration/adjustment versions.

Unknown measurement keys go into a collapsed “Additional measurements” table.
This makes the client forward-compatible while purpose-built renderers are
added for new detector versions.

## 13. Security search and technical fingerprint

### Search API addition

```http
GET /api/securities?query=rel&pageSize=10
```

Return only eligible matches:

```json
{
  "items": [
    {
      "isin": "INE...",
      "symbol": "RELIANCE",
      "name": "Reliance Industries Limited",
      "sectorName": "Energy",
      "lastTradingDate": "2026-09-04"
    }
  ]
}
```

`SecuritySearch` behavior:

- start after two characters;
- debounce for approximately 250 ms;
- abort the previous request when input changes;
- support Arrow Up/Down, Enter, Escape, and pointer selection;
- expose combobox/listbox ARIA semantics;
- show symbol, name, and sector;
- navigate to `/securities/{encodedIsin}`;
- never send a request for blank input.

### Fingerprint API

```http
GET /api/securities/{isin}/fingerprint?asOf=2026-09-04
```

Response sections:

```json
{
  "security": {},
  "dataAsOf": "2026-09-04",
  "trend": {},
  "primarySetup": {},
  "compression": [],
  "momentum": [],
  "relativeStrength": {},
  "volume": {},
  "location": {},
  "context": {},
  "scores": {},
  "activePatterns": [],
  "recentEvents": [],
  "lineage": {}
}
```

The fields map directly to specification section 132: Stage 2 and HH/HL,
primary setup/variant/state, maturity, compression, momentum, RS1M/3M/6M/12M,
volume contraction, distance from 52-week high/pivot/EMA20/SMA50, market and
sector context, pattern quality, and setup score.

### Security page

- Header with symbol, company name, sector, close, change, and data date.
- Technical fingerprint summary.
- Adjusted price chart.
- Active primary setup and supporting signals.
- Score breakdown and location measurements.
- Active/recent pattern list linking to pattern details.
- Recent event timeline.
- No-setup state that still shows trend, relative strength, and chart data.

## 14. Chart-series API and component

### Chart API addition

```http
GET /api/securities/{isin}/chart?from=2026-01-01&to=2026-09-04&adjusted=true&include=ema20,sma50,sma200,volume,events
```

Response:

```json
{
  "security": { "isin": "INE...", "symbol": "EXAMPLE" },
  "from": "2026-01-01",
  "to": "2026-09-04",
  "adjusted": true,
  "priceScale": "linear",
  "bars": [
    {
      "date": "2026-09-04",
      "open": 488.0,
      "high": 496.0,
      "low": 486.5,
      "close": 491.5,
      "volume": 1234567,
      "ema20": 481.3,
      "sma50": 463.2,
      "sma200": 410.8
    }
  ],
  "levels": [
    { "kind": "PIVOT", "price": 500.0, "startDate": "2026-07-15", "endDate": null }
  ],
  "events": [
    { "date": "2026-09-04", "eventType": "TRIGGERED", "patternInstanceId": "..." }
  ],
  "corporateActions": []
}
```

The server returns already adjusted and downsampled data appropriate to the
requested range. The client does not apply split/bonus factors.

### `PatternChart`

Implement the first chart with semantic SVG and a separate accessible summary
table. Required layers:

- price path or OHLC marks;
- EMA20, SMA50, and SMA200 toggles;
- volume panel;
- pivot, support, and invalidation levels;
- highlighted pattern date window;
- lifecycle markers;
- tooltip driven by pointer and keyboard-selected date;
- legend that does not rely on color alone.

Use CSS custom properties from `topology.css`. Resize with `ResizeObserver` and
recompute only display geometry, not financial values. If later profiling
shows that a chart library is warranted, select it through a separate decision
record after testing bundle size, keyboard accessibility, mobile behavior, and
licensing.

## 15. Shared domain presentation rules

### Lifecycle badges

Map states to tone, icon/shape, and text. Color alone is insufficient.

| State group | States | Presentation intent |
|---|---|---|
| Developing | `DETECTED`, `FORMING` | Quiet neutral |
| Actionable | `MATURE`, `READY` | Warm amber |
| Active | `TRIGGERED`, `CONFIRMED` | High emphasis |
| Terminal | `FAILED`, `INVALIDATED`, `EXPIRED` | Muted warning/error |

Use the server state verbatim in accessible text.

### Scores

- Render 0–100 with at most one decimal.
- Clamp only the visual fill, never the displayed value.
- A missing score renders “Not available”.
- Show named components and configured weights when provided.
- Add the statement “Ranking score, not historical probability.” beside setup
  score wherever confusion is plausible.

### Prices and percentages

Create pure formatters:

```js
formatPrice(value, currency = 'INR')
formatPercent(value, { signed = false } = {})
formatScore(value)
formatCompactNumber(value)
formatMarketDate(value)
```

Use `Intl.NumberFormat('en-IN')`. Preserve server units: a `...Pct` value of
`1.7` displays as `1.7%`, not `170%`. Positive location distance may have a
leading plus sign; negative distance keeps its minus sign.

### Pattern-specific measurement groups

- VCP: duration, depth, contraction count/list, ATR compression, volume
  compression, pivot distance.
- Flat base: duration, depth, range compression, support/resistance tests.
- 52-week high base: high distance, duration near high, depth.
- Breakout: resistance type, tests, buffer, close above pivot, volume
  expansion, confirmation/failure window.
- Breakout retest: source breakout, sessions since breakout, retest depth,
  hold/reclaim evidence.
- EMA20/SMA50 pullbacks: touch number, pullback depth/duration, MA slope,
  rejection/reclaim, invalidation.
- Failure: source pattern, violated level, maximum advance, days above pivot,
  structural evidence.

## 16. Data-fetching hook

Create a small `useApiResource(key, loader)` hook only after two pages need the
same lifecycle. It should expose:

```js
{
  data,
  error,
  status, // idle | loading | refreshing | success | error
  reload,
}
```

Rules:

- Each effect creates an `AbortController`.
- Cleanup aborts the request.
- The resource key includes every input that changes the response.
- An aborted request never shows an error.
- A late response cannot overwrite a newer request.
- Refreshing retains previous data but announces the refresh unobtrusively.
- Do not introduce a global cache in V1.
- Page components decide empty-state wording because it is domain-specific.

## 17. Loading, empty, error, and stale states

Every server-backed region must define all states before implementation.

| State | Required behavior |
|---|---|
| Initial loading | Shape-matched skeleton and `aria-busy="true"` |
| Refreshing | Keep prior content, show small progress status |
| Empty | Explain filters/date and offer a useful action |
| Partial | Render valid sections and identify unavailable sections |
| Stale | Show data date and stale banner |
| Unauthorized | Clear token and replace navigation to login |
| Forbidden | Explain access limitation |
| Not found | Resource-specific not-found page |
| Network/server error | Retry without losing URL filters |

Use an `aria-live="polite"` status region for completed loads, filter result
counts, and recoverable errors. Avoid repeated announcements for every
skeleton element.

## 18. Responsive layout and design tokens

All new styling consumes `topology.css`. Extend it only with reusable semantic
tokens, then consume those tokens from `styles.css`.

Potential additions, if equivalent tokens do not already exist:

```css
--layout-content-max;
--layout-reading-max;
--size-app-header;
--size-filter-sidebar;
--size-touch-target;
--space-chart-gap;
--color-state-developing;
--color-state-actionable;
--color-state-active;
--color-state-terminal;
--duration-request-transition;
```

Do not put raw repeated colors, radii, shadows, spacing, font size, or control
heights into page rules when an existing token represents the value.

### Breakpoints

- Wide desktop: shell with persistent navigation and filter sidebar.
- Tablet/compact desktop at the established `980px` breakpoint: collapse
  secondary columns and use filter drawer.
- Mobile: one-column cards, compact header, full-width actions, and at least
  44px touch targets.
- Very narrow widths around 320px: no clipped score labels, chart controls, or
  breadcrumb text.

Data density may reduce on mobile, but critical evidence must remain reachable
through expansion, not disappear.

## 19. Accessibility requirements

- One `h1` per page and ordered heading levels.
- A skip link to main content in `AppShell`.
- Native buttons, links, forms, tables, and details elements where appropriate.
- Visible focus using the established amber focus token.
- Tables include captions or accessible names and scoped column headers.
- Sort buttons announce column and direction.
- Filters have visible labels and error associations.
- Drawers/dialogs manage focus and close with Escape.
- Chart information has an accessible textual/table alternative.
- Score and state meaning never depends only on color.
- Loading and result changes use restrained live-region announcements.
- Respect `prefers-reduced-motion`.
- Test keyboard-only use at desktop and mobile widths.

## 20. Security and privacy

- Keep the access token only in `sessionStorage` under the established key.
- Never put it in URL parameters, component text, analytics, or logs.
- Render server text as normal React text; do not use `dangerouslySetInnerHTML`.
- Allow only known relative client routes in navigation helpers.
- Treat cursors as opaque and encode them with `URLSearchParams`.
- Do not expose raw backend stack traces or upstream NSE error payloads.
- Do not persist market responses or user data to local storage in V1.
- Clear user and all protected in-memory data during sign-out.
- When a `401` occurs, abort other protected requests where practical.
- Keep CSP and security-header work at the deployment/server layer, with the
  client avoiding inline scripts that would complicate that policy.

## 21. Performance requirements

- Request paginated setup data; never download the full universe.
- Keep default page size at 25.
- Debounce search, not filter buttons that explicitly apply changes.
- Abort superseded requests.
- Lazy-load route-level pages with `React.lazy` only when production bundle
  measurement shows a useful reduction; authentication must remain in the
  eagerly loaded shell.
- Limit the default chart range and let the server downsample long periods.
- Memoize chart geometry only after measurement demonstrates a render issue.
- Avoid rendering hidden desktop and mobile copies of the entire setup list.
- Establish production-build budgets after the first real overview and chart
  are built, then record them in this document or a dedicated decision record.

## 22. Research UI and APIs — later phase

Research is not part of the first product slice, but its client contract must
preserve the specification's distinction between ranking and outcomes.

### Create run

```http
POST /api/research/runs
Content-Type: application/json
Authorization: Bearer <token>

{
  "patternType": "BASE-VCP",
  "dateFrom": "2018-01-01",
  "dateTo": "2026-09-04",
  "filters": {
    "minRs6m": 90,
    "supportingPatterns": ["TREND-S2"],
    "minMarketRegimeScore": 70,
    "minSectorScore": 80,
    "maxVolumeCompression": 0.60
  }
}
```

Return `202 Accepted` with `runId`, `status`, and status URL. The client polls
with capped backoff while the page remains visible, stops on terminal state,
and offers explicit retry for a failed run.

### Results

Render sample count first, then median 5/10/20/40/60-session returns, MFE, MAE,
days-to-threshold, and hit-before-loss measurements. Clearly show:

- universe and date range;
- engine/configuration/data versions;
- point-in-time membership policy;
- survivorship-bias policy, including delisted and historically eligible
  securities;
- filters used;
- missing-data count;
- inadequate-sample warning;
- comparison against an unfiltered baseline when supplied.

Never combine setup score and observed probability into one gauge.

## 23. Testing strategy

The frontend currently has no test runner. Add tests when the first product API
integration is implemented, selecting the smallest maintained setup compatible
with Vite and React. The expected stack is Vitest, React Testing Library, and
user-event, but dependency addition should occur in the implementation change,
not as a documentation-only change.

### Unit tests

- route parsing and path builders;
- query serialization and URL filter parsing;
- API error conversion and legacy auth error compatibility;
- date, score, price, percent, and compact-number formatters;
- lifecycle presentation mapping;
- unknown enum and null-value handling;
- authentication session helpers.

### Component tests

- setup table/card renders the same core fields;
- sorting requests the server and updates the URL;
- filter apply/clear behavior;
- score breakdown disclosure;
- fingerprint with complete, partial, and no-primary-setup data;
- timeline ordering and event expansion;
- search keyboard navigation and request cancellation;
- stale, loading, empty, error, 401, 403, and 404 states;
- sign-out clears protected content and Back cannot restore it.

### API contract fixtures

Store small sanitized fixtures under `src/frontend/src/test/fixtures/` for:

- overview success/stale/partial;
- setup pages with and without a next cursor;
- each major pattern family measurement shape;
- complete and partial fingerprints;
- chart bars/levels/events;
- pattern event history;
- structured errors.

Fixtures describe the agreed wire contract and must not contain live tokens or
large copied production payloads.

### Browser verification

For every page verify:

- 320px, 390px, 768px, 980px, and common desktop widths;
- no unintended document-level horizontal scroll;
- auth screens retain no unnecessary vertical scroll at normal desktop size;
- keyboard-only completion of every action;
- visible focus and readable contrast;
- Back/Forward route and filter restoration;
- direct loading of dynamic URLs through Vite fallback;
- expired token redirection;
- console contains no React warnings or failed requests.

### Build gate

Run:

```powershell
cd src\frontend
npm run build
```

When tests are introduced, add a stable `npm test` script and run it before the
production build.

## 24. Client delivery phases

### Client Phase 0 — Contract fixtures and foundation

**Status: Complete — 2026-09-09.**

1. Freeze common error, freshness, setup summary, pattern detail, event,
   fingerprint, and chart response examples with the backend.
2. Add `apiClient.js`, API modules, session helpers, route parser, query helper,
   guards, and formatters.
3. Refactor existing auth calls through `authApi.js` without changing visible
   behavior.
4. Add not-found and application-level session states.
5. Add unit tests for the foundation.

**Gate:** login, registration, refresh validation, sign-out, and current routes
still work; API errors have one representation.

### Client Phase 1 — Real overview vertical slice

**Status: Complete — 2026-09-09.**

1. Implement `GET /api/overview` on the server.
2. Replace overview placeholders with freshness, pipeline, market regime,
   breadth, lifecycle counts, and top setups.
3. Build `AppShell`, shared navigation, skeleton, empty, error, and stale
   components.
4. Link count cards to URL-prefiltered setup routes.
5. Verify responsive and authenticated behavior.

**Gate:** after the daily engine completes, a user can see when data was
processed and which opportunities rank highest.

### Client Phase 2 — Screener and filters

**Status: Complete — 2026-09-09.**

1. Implement `GET /api/setups` with server pagination, sorting, and facets.
2. Build `SetupsPage`, desktop table, mobile cards, filters, and cursor controls.
3. Make filter and sort state reproducible from the URL.
4. Cover cancellation, empty filters, invalid filters, and stale data.

**Gate:** users can find setups by family, variant, lifecycle, score, sector,
relative strength, liquidity, and market date without loading the universe.

### Client Phase 3 — Pattern evidence

**Status: Complete — 2026-09-09.**

1. Implement `GET /api/patterns/{id}` and `/events`.
2. Build pattern header, measurement groups, score breakdown, supporting
   signals, lineage, and timeline.
3. Add generic fallback display for future measurements.
4. Link every setup row/card to its detail page.

**Gate:** every displayed ranking can be inspected down to its measurements,
levels, supporting evidence, versions, and lifecycle transitions.

### Client Phase 4 — Security fingerprint and search

**Status: Complete — 2026-09-09.**

1. Implement `GET /api/securities` search and fingerprint endpoint.
2. Add accessible debounced search to `AppShell`.
3. Build the complete technical fingerprint page.
4. Show useful technical state even when no primary setup exists.

**Gate:** users can locate any eligible stock and understand its current
technical classification.

### Client Phase 5 — Adjusted chart integration

**Status: Complete — 2026-09-09.** The existing `lightweight-charts`
decision is retained instead of introducing a second SVG chart renderer.

1. Implement the chart-series endpoint with bounded/downsampled adjusted data.
2. Build accessible SVG price/volume chart and summary table.
3. Add moving averages, levels, pattern windows, actions, and event markers.
4. Embed the chart in security and pattern detail pages.

**Gate:** the visible geometry agrees with server measurements and remains
usable with keyboard, mobile, and reduced-motion settings.

### Client Phase 6 — Research

**Status: Complete — 2026-09-09.** The client polls non-terminal runs and
renders baseline comparison only when the server supplies one; it never
fabricates an unfiltered baseline or exposes cancellation when unsupported.

1. Freeze asynchronous research run contracts.
2. Build filter builder, job status, cancellation if supported, result summary,
   and baseline comparison.
3. Display sample adequacy and point-in-time lineage.
4. Add shareable read-only research URLs if authorization permits.

**Gate:** a user can reproduce a historical query and distinguish observed
outcomes from the current setup score.

### Client Phase 7 — Hardening

**Status: Complete — 2026-09-09.**

1. Complete accessibility and browser checks.
2. Measure request count, render cost, chart behavior, and production bundle.
3. Add observability hooks without capturing tokens or sensitive payloads.
4. Verify every error/empty/stale/partial state against a real backend.
5. Update `AGENTS.md` if architecture or stable frontend conventions changed.

**Gate:** production build, automated tests, responsive checks, protected-route
checks, and API contract tests all pass.

## 25. Server/client dependency map

| Client capability | Required server capability | Can proceed with fixture first? |
|---|---|---|
| Authentication | login/register/me | Already available |
| Overview | overview aggregation | Yes |
| Setup screener | query service, pagination, facets | Yes |
| Pattern detail | instance repository/service | Yes |
| Timeline | immutable event history | Yes |
| Security fingerprint | feature/pattern/context aggregation | Yes |
| Security search | eligible-security query | Yes |
| Chart | adjusted bars, features, levels, events | Yes |
| Research | asynchronous backtest/result service | Yes |

Fixture-first means UI development may begin against checked-in contract
fixtures, but completion requires integration with the real endpoint and error
behavior.

## 26. Decisions to lock before implementation

1. Whether registration signs the user in or returns to login.
2. Whether setup multi-select filters use repeated query keys or comma-separated
   values; repeated keys are recommended.
3. Whether pagination is cursor-only or also exposes an estimated total; cursor
   is the source of truth.
4. Default overview and screener `asOf` behavior when the latest pipeline run is
   partial or failed.
5. Which lifecycle states count as “active” in overview totals.
6. Stable market-regime labels and their accessible explanations.
7. Default chart range and maximum returned points.
8. Whether chart prices are exclusively adjusted or allow an explicitly
   labelled raw-price comparison.
9. Minimum research sample size before displaying probability-like statistics.
10. Whether admin-only pipeline diagnostics belong in the normal overview or a
    later protected operations page.

## 27. Client definition of done

The client implementation is complete when:

- every protected route validates the session and handles expiry safely;
- all HTTP calls pass through the shared client and relative Vite-proxied API;
- the overview states its exact EOD freshness and pipeline state;
- setup filters, sorting, pagination, and selected date survive URL sharing and
  browser navigation;
- users can inspect every setup's evidence, scores, levels, supporting patterns,
  lifecycle timeline, and lineage;
- users can search an eligible security and view its complete technical
  fingerprint;
- charts use server-adjusted data and visually agree with stored measurements;
- loading, refreshing, empty, partial, stale, unauthorized, forbidden,
  not-found, and server-error states are implemented;
- setup score is never presented as historical probability;
- desktop, tablet, and mobile layouts remain usable without accidental scroll;
- keyboard and screen-reader alternatives exist for filters, tables, charts,
  and timelines;
- automated tests and `npm run build` pass;
- integration is verified against the real backend, not only fixtures.
