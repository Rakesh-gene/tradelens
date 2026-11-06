# FYERS market-data provider assessment

Status: conditional; authentication and commercial rights require written confirmation  
Reviewed: 2026-09-21

## Conclusion

FYERS can technically supply TradeLens EOD data, but a personal FYERS API app is
not yet proven suitable for the unattended production pipeline.

The positive findings are:

- API V3 exposes daily historical OHLCV through `/data/history`.
- Existing applications can operate in data-only mode after the April 2026 API
  trading changes.
- FYERS publishes a daily symbol master containing ISIN, which fits TradeLens's
  stable security identity.
- A refresh-token endpoint exists, and FYERS says refresh tokens have a 15-day
  validity.

The blocking ambiguity is authentication. FYERS also states that, from April 1,
2026, daily 2FA is required and continuous refresh-token sessions are not
supported. Its public material does not clearly say that a data-only app is
exempt. Even the older 15-day refresh behavior would still require periodic
manual authorization and would not meet TradeLens's zero-touch requirement.

Do not automate FYERS login, PIN, OTP, or TOTP. Use FYERS only if it confirms a
supported unattended authentication method for a data-only application.

## Proposed pipeline configuration

Keep NSE as the equity-list and classification source. If FYERS clears the two
approval gates below, extend the existing selection to:

```text
MARKET_DATA_PROVIDER=NSE
MARKET_DATA_PROVIDER=FYERS
```

With `FYERS`, a run performs:

1. NSE equity-list and classification download.
2. FYERS symbol-master download and exact ISIN mapping.
3. FYERS daily historical OHLCV download.
4. Provider revision and corporate-action anomaly checks.
5. Canonical bars, features, patterns, and research rebuild.

There is no NSE candle download and no provider fallback inside that run.

## Authentication gate

FYERS user-app authentication redirects a browser to obtain an `auth_code`, then
exchanges it using a SHA-256 hash of the app ID and secret. The response may
include a refresh token. Official support currently presents two rules that need
reconciliation:

- a refresh token remains valid for 15 days; and
- the April 2026 retail API regime requires daily 2FA and does not support
  continuous refresh-token sessions.

Ask FYERS this exact question:

> TradeLens is a server-side, data-only application. It never places or modifies
> orders. It runs an unattended EOD historical-data import at 19:00 Asia/Kolkata.
> Can a personal FYERS API application renew access indefinitely through a
> documented refresh-token or service-token flow without daily or periodic
> browser login, OTP, TOTP, or PIN entry after April 1, 2026?

If the answer is no, FYERS does not meet the operational requirement. If the
answer is yes, request the endpoint, token-rotation rules, expiration behavior,
revocation conditions, and written confirmation that the method is supported for
production data-only use.

## Commercial-use gate

TradeLens is a paid customer-facing product. FYERS describes its real-time market
data API as informational and non-commercial unless separately licensed, and it
has a separate process for third-party applications.

Ask FYERS to confirm in writing that TradeLens may:

- store ten years of NSE daily OHLCV;
- retain provider revisions and backups;
- compute and store features, patterns, scores, and research results;
- display historical charts and derived analytics to paying customers;
- serve customers who are not FYERS account holders; and
- retain reproducible historical results after raw source data is revised.

Also ask what exchange permission, attribution, delay label, retention limit,
pricing, and audit obligations apply.

## Historical data behavior

The history endpoint supports daily candles with records in the form
`[epoch, open, high, low, close, volume]`. Current FYERS developer material states
that day, week, and month requests are limited to 366 days, so a ten-year backfill
requires roughly ten requests per security.

Current standard account limits are documented as 10 requests per second, 200
requests per minute, and 100,000 requests per day. At 2,300 equities and about ten
history chunks each, the initial backfill is feasible but takes at least about two
hours at the minute limit before retries and validation. It must be resumable.

## Identity and universe

The FYERS symbol master contains ISIN, unlike Zerodha's instrument dump. Join it
to the NSE equity list using ISIN first and validate exchange, series, and symbol.
Store an effective-dated mapping:

```text
(provider, fyers_symbol, fy_token, isin,
 effective_from, effective_to, observed_at)
```

NSE continues to define eligibility. The FYERS master only resolves provider
symbols and tokens. Missing or conflicting ISIN mappings are pipeline failures,
not reasons to remove an NSE equity from the universe.

## Corporate actions

FYERS documents automatic corporate-action handling for holdings and adjusted
pricing on its charts, but the reviewed public documentation does not explicitly
promise that `/data/history` returns fully back-adjusted OHLCV for every supported
action. Do not infer API behavior from portfolio or chart behavior.

Before using provider-adjusted mode:

- ask FYERS which corporate actions adjust historical API OHLC and volume;
- ask when revised history becomes available and whether revisions are notified;
- test splits, bonuses, rights issues, demergers, spin-offs, and extraordinary
  dividends;
- include ABFRL, VEDL, ITC, and RELIANCE in the contract fixture set; and
- retain gap detection, revision checksums, quarantine, and downstream
  invalidation.

If FYERS confirms and the test passes, use `PROVIDER_ADJUSTED` with factors of
`1`. Otherwise retain TradeLens corporate-action ingestion and rebuilding.

## Go/no-go sequence

1. Ask FYERS support to resolve unattended data-only authentication.
2. Obtain written commercial storage and customer-display permission.
3. Create a data-only app only after both answers are acceptable.
4. Run an isolated authentication and historical-data spike.
5. Add `FYERS` to `MARKET_DATA_PROVIDER` only after the spike passes.

Until then, keep `MARKET_DATA_PROVIDER=NSE`.

## Official references

- [FYERS user-app authentication](https://support.fyers.in/portal/en/kb/articles/how-does-the-authentication-and-login-flow-work-for-user-apps-on-fyers)
- [FYERS refresh-token validity](https://support.fyers.in/portal/en/kb/articles/what-is-the-function-of-the-refresh-token-in-fyers)
- [FYERS April 2026 API authentication changes](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026)
- [FYERS data-only mode](https://support.fyers.in/portal/en/kb/articles/how-do-i-activate-the-new-app-for-api-trading-after-april-1-2026)
- [FYERS symbol master](https://support.fyers.in/portal/en/kb/articles/where-can-i-find-the-most-up-to-date-symbols-for-different-exchanges)
- [FYERS API overview](https://myapi.fyers.in/)
