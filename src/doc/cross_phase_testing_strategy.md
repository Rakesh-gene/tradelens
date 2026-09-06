# TradeLens cross-phase testing strategy

This document implements section 18 of the positional trading pattern engine
plan. The normal suite is deterministic and network-free. Live exchange
contracts and production-volume benchmarks are explicit opt-in gates so an NSE
outage or a long benchmark cannot make ordinary development tests flaky.

## Representative security and source provenance

Reliance Industries Limited is the cross-phase representative:

- symbol: `RELIANCE`;
- ISIN: `INE002A01018`;
- source: NSE India;
- history snapshot: 1–5 January 2024;
- action snapshot: the 19 August 2024 dividend and 28 October 2024 1:1 bonus;
- fixture: `src/backend/fixtures/nse/reliance_phase18_snapshot.json`.

The snapshot was downloaded through `NseApiClient` on 5 September 2026. It is
small enough to audit and contains NSE's current camel-case history response,
not a hand-authored substitute. The integration tests parse the source shape
before converting it to internal records. Refreshing the snapshot is a
deliberate review operation; normal tests never rewrite it.

Run the read-only live contract gate from `src/backend`:

```powershell
py -3.11 -m data_pipeline.cli verify-nse-contract `
  --symbol RELIANCE `
  --from-date 2024-01-01 --to-date 2024-01-05 `
  --actions-from 2024-07-01 --actions-to 2024-11-30
```

The same contract is available as an opt-in test:

```powershell
$env:TRADELENS_RUN_LIVE_NSE_TESTS = "1"
py -3.11 -m unittest test_live_nse_contract -v
```

Never enable that variable in the deterministic CI job. Schedule it separately
with bounded frequency and surface NSE block, timeout, or schema failures as an
external-contract alert.

## Test layers and ownership

| Layer | Coverage | Primary tests |
| --- | --- | --- |
| Unit | formulas, boundaries, parsers, true/false/insufficient detector cases, scores and transitions | `test_features.py`, `test_nse_api.py`, detector modules, `test_pattern_lifecycle.py` |
| Repository | append-only migrations, upsert idempotency, checkpoints, pattern deduplication/events, pagination and filters | `test_market_data_repository.py`, `test_pattern_repository.py`, `test_pattern_queries.py`, `test_research_repository.py` |
| Cross-phase integration | NSE payload → raw → adjusted → features; adjusted data → swings/zones → detected candidate → immutable event; correction recomputation | `test_cross_phase_strategy.py` |
| HTTP integration | JWT protection plus overview, setup, detail, fingerprint, and research contracts | `test_app.py` |
| Golden scenarios | named V1 pattern inventory, rationale, pivot/state/measurement/score expectations | `fixtures/golden/pattern_scenarios.json` and detector regression tests |
| Non-functional | recovery, duplicate daily runs, retries, volume, universe runtime, responsive UI | research/delta/NSE tests, Phase 18 benchmark, operations benchmark, UI gate below |

The catalog test fails if a V1 pattern identifier loses traceability or a named
scenario omits its rationale or expected output contract. Numeric behavior
continues to live beside each detector so threshold failures identify the
responsible module directly.

## Required commands

Run the complete deterministic backend suite from the repository root:

```powershell
py -3.11 -m unittest discover -s src\backend -p "test*.py" -v
```

Run the six-million-row, bounded-memory ingestion-boundary benchmark from
`src/backend`. This intentionally does not contact NSE or insert synthetic rows
into the application database:

```powershell
py -3.11 -m benchmarks.phase18 --rows 6000000 --batch-size 10000
```

Measure the real detector stack over the database universe after a completed
import. Omit `--max-securities` for the release gate:

```powershell
py -3.11 -m operations.cli benchmark-scan --as-of 2026-09-04
```

Record machine specification, universe size, versions, duration, throughput,
failures, and the configured 120-minute daily window with release evidence.
Do not relax deterministic thresholds in response to a performance result.

## Responsive and accessibility release gate

Build the frontend, run local services, and test the authenticated overview,
setups, security fingerprint, and pattern detail routes at 320px and 390px.
For each viewport confirm:

- `document.documentElement.scrollWidth <= window.innerWidth`;
- all controls have an accessible name;
- Tab and Shift+Tab reach every interactive control in visual order;
- focus indication remains visible against the dark surface;
- Enter/Space operate native buttons and links;
- sign-out clears the session and browser Back cannot reveal protected content;
- the browser console contains no errors.

This is a release gate until a browser-test dependency is deliberately adopted.
Do not add a routing or testing framework solely to automate this check.

## Failure interpretation

- Deterministic suite failure: application regression; block the change.
- Live NSE contract failure: classify transport, blocking, or schema drift;
  preserve the last reviewed fixture and investigate the client boundary.
- Volume/runtime gate failure: preserve detector semantics, profile the named
  stage metrics, and optimize batching/query execution.
- Responsive/accessibility failure: fix the component or token rule and repeat
  both viewports and keyboard traversal.
