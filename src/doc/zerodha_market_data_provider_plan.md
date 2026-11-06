# Zerodha market-data provider proposal

Status: blocked for a standard Kite Connect app; conditional on approved platform access  
Reviewed: 2026-09-21

## Decision

TradeLens will continue to download its eligible equity list and classifications
from NSE. Daily OHLCV will come from exactly one provider selected at process
startup:

```text
MARKET_DATA_PROVIDER=NSE       # existing behavior and default
MARKET_DATA_PROVIDER=ZERODHA   # NSE equity list, Zerodha OHLCV
```

A pipeline run never downloads candles from both providers. It snapshots the
selected value in its parent import-run record, and every child stage uses that
same value. There is no silent provider fallback.

Creating a normal Kite Connect app is sufficient for a technical spike. It is
not sufficient for a paid customer-facing product. Kite Connect's standard terms
prohibit permanent databases, redistribution, derivative works, and public
display of API content unless Zerodha expressly permits them. Obtain written
permission from Zerodha and any required exchange approval before production
use.

The scheduled pipeline must be unattended. A standard Kite Connect app therefore
does not qualify: its supported authentication flow requires a person to sign in
and authorize the app each trading day. Do not automate the Zerodha login page,
credentials, or TOTP. Proceed with Zerodha only if it grants TradeLens approved
platform access with a documented, unattended token-renewal mechanism.

## Pipeline shape

```text
NSE equity master ---> eligible equities keyed by ISIN
                              |
                              +--> configured OHLCV provider
                                     |-- NSE history, or
                                     `-- Zerodha history
                                               |
                                               +--> quality and revision checks
                                               `--> canonical adjusted bars
                                                          |
                                                          `--> features -> patterns -> research
```

The equity-list and classification stages always use `NseApiClient`. With
`MARKET_DATA_PROVIDER=ZERODHA`, the history backfill, daily delta, and supported
benchmark-history stages use `ZerodhaApiClient` and do not request NSE candles or
NSE corporate actions.

If Zerodha authentication is absent, expired, rate limited, or unavailable, the
price stage fails visibly and retains its checkpoint. It must not fetch NSE
candles because that would mix lineage within a run.

## Kite login flow

Kite Connect uses a browser login and proprietary token exchange. It resembles
OAuth but is not a standard OAuth 2.0 authorization-code flow.

1. An administrator starts the connection from TradeLens.
2. TradeLens redirects the browser to
   `https://kite.zerodha.com/connect/login?v=3&api_key=...`.
3. Zerodha redirects to the registered callback with a short-lived
   `request_token`.
4. The backend computes `SHA256(api_key + request_token + api_secret)` and posts
   it to `POST https://api.kite.trade/session/token`.
5. The backend stores the returned access token encrypted and sends API requests
   with `Authorization: token api_key:access_token` and `X-Kite-Version: 3`.

The API secret and access token remain server-side. The callback validates a
short-lived, single-use signed nonce passed through `redirect_params` and
requires the initiating TradeLens user to be an administrator.

A normal access token expires during Zerodha's next beginning-of-day cycle. The
documentation describes expiry at 06:00 the next day and limits refresh tokens
to approved platforms. TradeLens should treat each token as valid only for its
stated trading day and expose `connected`, `expires soon`, and
`reconnect required` states. Unattended daily ingestion needs approved platform
access or a daily administrator login.

Server configuration:

```text
KITE_API_KEY=...
KITE_API_SECRET=...
KITE_REDIRECT_URI=https://<api-host>/api/admin/integrations/zerodha/callback
```

Validate the Kite settings only when `MARKET_DATA_PROVIDER=ZERODHA`. Never put
the API secret or access token in the frontend, logs, or repository.

## Approval questions for Zerodha

Send Zerodha a precise TradeLens use-case description and obtain written answers:

1. May TradeLens store ten years of daily OHLCV for the full NSE equity universe?
2. May it calculate and retain adjusted features, patterns, scores, and research
   results derived from those candles?
3. May paying TradeLens customers view derived results and historical charts?
4. Must every customer be a Zerodha client and authenticate separately?
5. Which exchange market-data and display approvals are required?
6. Can TradeLens receive platform approval and unattended read-only access?
7. Do retention rights cover backups, disaster recovery, and audit fixtures?
8. Is corporate-action adjustment behavior contractual, including correction
   timing, volume treatment, and notifications?
9. How can TradeLens retrieve history for delisted instruments whose tokens no
   longer appear in the current instrument dump?
10. What pricing, support, service level, and rate limits apply?

Implementation beyond an isolated spike is blocked until storage, derived
analytics, customer display, and unattended token renewal are covered in writing.

## Provider boundary

Add a focused `HistoricalMarketDataProvider` protocol under `data_pipeline/`:

- `fetch_daily_bars(instrument, from_date, to_date)`;
- `fetch_benchmark_bars(instrument, from_date, to_date)` where supported;
- provider identity and adjustment mode; and
- source timestamp and revision metadata.

Implement the existing NSE path and a new `ZerodhaApiClient` behind a provider
factory. Read `MARKET_DATA_PROVIDER` once at startup, normalize it to uppercase,
and reject any value except `NSE` or `ZERODHA`.

`ZerodhaApiClient` owns its signing headers, error mapping, timeouts, retry
policy, and a process-wide limiter capped at three historical requests per
second. A daily-candle request can cover at most 2,000 calendar days, so a
ten-year backfill needs two chunks for each currently tradable security.

The provider protocol does not own the NSE security master, classifications, or
calendar. `NseDataCollector.DownloadEquities()` remains the public equity-list
job regardless of the configured price provider.

## Mapping Zerodha instruments to NSE equities

Zerodha's instrument dump does not contain ISIN, but its historical endpoint
requires an `instrument_token`. Fetch and retain the instrument dump once each
morning around 08:30, as Zerodha recommends, solely for provider lookup.

Add an effective-dated mapping:

```text
(provider, instrument_token, exchange, trading_symbol,
 isin, effective_from, effective_to, observed_at)
```

Match each Zerodha `NSE`/`EQ` row to the current NSE equity master by exact
exchange and trading symbol. Retain the NSE ISIN as the stable TradeLens identity.
Quarantine missing or ambiguous mappings; never use a symbol as permanent
identity.

The NSE equity list still defines the universe. A current Zerodha dump cannot
resolve a delisted security that lacks a live token, so the pipeline must report
that security as unavailable instead of silently removing it.

## Raw and canonical storage

Do not write Zerodha rows into `nse_daily_bars_raw`. Its primary key is only
`(isin, trading_date)`, so doing that would overwrite NSE observations and lose
provenance.

Add provider-neutral source storage keyed by at least:

```text
(provider, provider_instrument_id, isin, trading_date, source_revision)
```

Store source checksum, retrieval time, import run, and raw OHLCV fields. Create a
canonical-bar selection that records the configured provider and source revision.
Existing NSE rows remain historical lineage but are not refreshed while Zerodha
is selected.

Changing `MARKET_DATA_PROVIDER` starts a new provider-specific data and
adjustment version. It does not rewrite or delete observations from the previous
provider. Downstream features and patterns rebuild from the newly selected
canonical version.

## Corporate actions and corrections

Add a `PROVIDER_ADJUSTED` source mode for Zerodha. Canonical OHLCV passes through
with price and volume factors of `1`; TradeLens does not apply its corporate
action factors on top of Zerodha candles and does not download NSE actions for
that run.

Keep the revision and quality stage. Zerodha says it adjusts historical data for
splits, bonuses, rights, spin-offs, and extraordinary dividends, but offers no
corporate-action API. Its support forum also records recent cases where API
series remained discontinuous after an action.

For Zerodha runs:

- run price-gap and volume anomaly checks after every import;
- quarantine suspect securities so patterns are not rebuilt from bad series;
- re-fetch a repair window daily;
- rotate full-history checksum reconciliation across the universe;
- create a new source revision when old candles change;
- rebuild adjusted bars, features, swings, zones, patterns, and affected research
  in dependency order; and
- keep the existing audited operator-resolution mechanism for exceptions.

This removes routine TradeLens factor calculation in Zerodha mode. It retains
corporate-action quality control because provider adjustments can be late or
incorrect.

## Delivery plan

### Phase 0: commercial go/no-go

- Obtain written Zerodha and exchange permission for the paid-product use.
- Confirm platform authentication, storage, display, derived-data, retention,
  and historical-universe rights.
- Record accepted terms and operational contacts.

Exit: written approval covers storage, analytics, customer display, and
unattended token renewal. Otherwise reject Zerodha as the OHLCV provider and
choose another licensed data vendor or retain the NSE pipeline.

### Phase 1: authentication

- Create the TradeLens Kite app with exact production and local callback URLs.
- Add server-only Kite configuration.
- Add admin-only connect, callback, status, and disconnect endpoints.
- Encrypt the access token at rest and log metadata only.
- On `TokenException`, mark the integration disconnected and alert an admin.

Exit: a token can be obtained, validated through `/user/profile`, expired, and
reconnected without exposing credentials.

### Phase 2: schema and mapping

- Add provider-neutral raw-bar and provider-instrument mapping migrations.
- Add the provider field to import-run lineage and checkpoints.
- Run the existing NSE equity-list import.
- Import the Zerodha instrument snapshot and map tokens to NSE ISINs.
- Report ambiguous, absent, inactive, and delisted mappings.

Exit: all eligible equities have a deterministic mapping or a visible failure.

### Phase 3: Zerodha data spike

- Select `MARKET_DATA_PROVIDER=ZERODHA` in a non-production environment.
- Fetch ten years of candles for RELIANCE, ITC, ABFRL, VEDL, renamed symbols,
  and inactive or delisted examples.
- Exercise recent splits, bonuses, rights issues, and demergers.
- Record throughput, missing dates, revisions, anomalies, and API errors.

The spike fetches no NSE candles.

Exit: coverage is sufficient and unexplained price or volume gaps are
quarantined.

### Phase 4: pipeline integration

- Add the provider factory to history backfill, daily delta, benchmark history,
  operations, and admin pipeline construction.
- Add resumable Zerodha chunking and the shared rate limiter.
- Add `PROVIDER_ADJUSTED` canonicalization and revision invalidation.
- Update status, checkpoints, metrics, and admin progress views.
- Keep the 19:00 Asia/Kolkata schedule, gated on a valid token and latest
  completed session.

Exit: offline fixtures and a Zerodha-configured full-universe run pass in a
non-production environment.

### Phase 5: configuration cutover

- Set `MARKET_DATA_PROVIDER=ZERODHA` for the target environment.
- Start a new provider-specific data and adjustment version.
- Rebuild downstream lineage from the Zerodha canonical series.
- Monitor freshness, mapping failures, token state, revisions, anomalies, and
  provider errors.

Rollback is an explicit configuration change to `MARKET_DATA_PROVIDER=NSE`
before starting a new run. A run already in progress never switches providers.

## App setup values

Use separate Kite applications for development and production because a Kite app
has one registered redirect URL.

For local development, expose the local backend through a stable HTTPS tunnel:

```text
Browser -> Zerodha login
        -> https://<stable-dev-tunnel>/api/admin/integrations/zerodha/callback
        -> tunnel forwards to http://127.0.0.1:<backend-port>
        -> local backend exchanges request_token for access_token
```

Register the tunnel URL on the development Kite app and set the same value in
`KITE_REDIRECT_URI`. Use a named Cloudflare Tunnel, reserved ngrok domain, or an
equivalent stable endpoint; an ephemeral URL would require editing the Kite app
on every restart.

The production Kite app registers only:

```text
https://<production-api-host>/api/admin/integrations/zerodha/callback
```

Zerodha also documents `http://127.0.0.1:<port>` as valid for local personal-app
testing because the browser, rather than Zerodha's server, follows the redirect.
The tunnel flow is the project default because it matches HTTPS production
behavior and avoids relying on developer-console localhost exceptions.

A postback URL is unnecessary for historical ingestion; postbacks are for order
updates.

## Source references

- [Kite Connect login and token exchange](https://kite.trade/docs/connect/v3/user/)
- [Kite Connect instruments](https://kite.trade/docs/connect/v3/market-data-and-instruments/)
- [Kite Connect historical candles](https://kite.trade/docs/connect/v3/historical/)
- [Kite Connect errors and rate limits](https://kite.trade/docs/connect/v3/exceptions/)
- [Kite Connect terms](https://kite.trade/terms/)
- [Zerodha statement on adjusted historical data](https://kite.trade/forum/discussion/15971/getting-the-right-closing-prices-adjusted-for-corporate-actions)
- [Recent adjustment defect report and Zerodha response](https://kite.trade/forum/discussion/16010/historical-candle-data-not-adjusted-after-corporate-actions-prices-show-20-single-day-gaps)
