# Trading performance review and improvement plan

Review date: 2026-09-06. Recorded trading sample: 2026-08-25 through 2026-09-04, nine sessions.

## 1. Executive conclusion

The observed losses are not explained by excessive exits alone. The immediate priorities are to make the evaluated strategy consistent with the deployed strategy, account for execution costs realistically, and distinguish protective exits from permission to enter a new position.

Confirmed findings:

- The 24 closed paper trades lost **INR 65,763.04 net**: INR 28,462.25 gross trading loss plus INR 37,300.79 recorded charges.
- Futures legs contributed **INR 52,308.93 net loss**, approximately 79.5% of the combined deficit. This is accounting attribution, not proof that removing futures produces a profitable strategy.
- The paper engine adds a directional future alongside the option spread; the live branch does not. These are materially different strategies and risks.
- Five reversal-warning exits contributed **INR 16,428.53 positive net P&L**. Fifteen session-close exits contributed **INR 61,882.59 negative net P&L**. This does not establish the counterfactual outcome of earlier or later exits.
- Order-flow data exists, but the trading filter is currently disabled. Only one replay session is recorded; its 58.9% three-minute directional hit rate is not evidence of profitable derivatives execution.
- All 24 closed trade totals reconcile to their recorded legs and charges within floating-point rounding. The negative totals are not a simple aggregation error.

Do not promote a threshold change, disable protective exits, increase size, or enable order flow merely to improve this small sample. First establish a reproducible, after-cost baseline and then run controlled out-of-sample comparisons. No strategy change here is a promise of profitability.

## 2. Scope and database discovery

The original workspace is `C:\MyData\repos\Tradelens`. Its EOD equity-pattern application does not own the paper ledger reviewed here.

Checking configuration identified the relevant implementation in the sibling repository **`C:\MyData\repos\MarketPlaygroud`** and the populated PostgreSQL database **`chatdb`**, selected by the shell's inherited `DATABASE_URL`. `restart_website.ps1` preserves that variable when present; backend `Settings.from_env()` also reads it. The fallback database named `signaldesk` was empty. TradeLens's local configuration selects a separate database named `tradelens`.

Database names are included to disambiguate evidence; credentials and connection strings are deliberately omitted. The inherited configuration identifies the data source available to this review, not independent proof of every currently running process's environment.

This document is saved in TradeLens's documentation folder because that is the current writable workspace. Unless explicitly labelled otherwise, source paths below are relative to **MarketPlaygroud**.

Reviewed critical paths include configuration, scheduling, model inference, direction/reversal decisions, FPI sizing, contract selection, paper/live execution, charges, persistence, order-flow capture/replay/gating, and walk-forward evaluation. This is a broad critical-path review, not certification of every line, every model artifact, or historical execution conditions. No strategy, settings, trades, services, or database contents were changed.

## 3. What the paper ledger actually shows

### 3.1 Market totals

All 24 records are `PAPER` and `CLOSED`; there are 69 recorded legs.

| Underlying | Trades | Gross P&L, INR | Charges, INR | Net P&L, INR | Net winners |
| --- | ---: | ---: | ---: | ---: | ---: |
| NIFTY | 17 | -25,353.25 | 30,511.62 | -55,864.87 | 6 |
| SENSEX | 7 | -3,109.00 | 6,789.17 | -9,898.17 | 4 |
| Combined | 24 | -28,462.25 | 37,300.79 | -65,763.04 | 10 |

Gross winners: 13/24 (54.2%). Net winners: 10/24 (41.7%). Three gross winners became net losers after charges. Net winning trades sum to INR 34,275.05; net losing trades sum to INR -100,038.09; realized net profit factor is approximately 0.343. Average net P&L is INR -2,740.13 per trade. Best/worst recorded trades are INR +17,252.47 / -31,145.79.

Charges represent approximately 56.7% of the absolute net deficit. They cannot all be treated as avoidable: removing them entirely would still leave a gross loss. Capital, margin and a continuous marked-equity series were not established, so this review does not claim return on capital, Sharpe, or portfolio maximum drawdown.

### 3.2 Leg attribution

| Underlying | Role | Legs | Gross P&L, INR | Charges, INR | Net P&L, INR |
| --- | --- | ---: | ---: | ---: | ---: |
| NIFTY | FUTURE | 14 | -14,235.00 | 28,109.18 | -42,344.18 |
| NIFTY | SHORT option | 17 | -7,517.25 | 1,348.70 | -8,865.95 |
| NIFTY | HEDGE option | 17 | -3,601.00 | 1,053.74 | -4,654.74 |
| SENSEX | FUTURE | 7 | -3,979.00 | 5,985.75 | -9,964.75 |
| SENSEX | SHORT option | 7 | +1,810.00 | 431.95 | +1,378.05 |
| SENSEX | HEDGE option | 7 | -940.00 | 371.48 | -1,311.48 |

Futures account for INR 34,094.93 of charges, approximately 91.4%. The remaining option-leg net attribution is INR -13,454.12. That is **not** an option-only backtest: removing futures may change sizing, exits, margin and subsequent actions. Some early trades also lack futures, so the whole sample is not a homogeneous strategy version.

### 3.3 Actual exit reasons

Exit reasons were obtained by joining `events(kind='trade_closed').payload.id` to `trades.id`. The `trades.reason` field contains entry rationale and must not be used as an exit reason.

| Exit reason | Trades | Gross P&L, INR | Charges, INR | Net P&L, INR |
| --- | ---: | ---: | ---: | ---: |
| 15:00 session exit | 15 | -44,023.25 | 17,859.34 | -61,882.59 |
| Confirmed direction reversal | 4 | -15,219.75 | 5,089.23 | -20,308.98 |
| Two strong opposing signals; reduced to flat | 5 | +30,780.75 | 14,352.22 | +16,428.53 |

A losing trade classified under an exit reason does not prove the exit caused the loss. To assess an exit, replay continuation versus closure using the same information available at that time, including executable prices and subsequent risk.

### 3.4 Session distribution

Grouped by entry date in Asia/Kolkata; amounts below are realized trade attribution, not an intraday equity curve.

| Entry session | Trades | Gross P&L, INR | Charges, INR | Net P&L, INR |
| --- | ---: | ---: | ---: | ---: |
| 2026-08-25 | 1 | -4,628.00 | 103.92 | -4,731.92 |
| 2026-08-26 | 2 | -588.25 | 242.72 | -830.97 |
| 2026-08-27 | 3 | -7,505.00 | 3,080.01 | -10,585.01 |
| 2026-08-28 | 2 | +482.25 | 2,043.20 | -1,560.95 |
| 2026-08-31 | 2 | -20,797.50 | 2,944.61 | -23,742.11 |
| 2026-09-01 | 2 | -34,017.75 | 3,790.09 | -37,807.84 |
| 2026-09-02 | 4 | +13,142.00 | 9,572.34 | +3,569.66 |
| 2026-09-03 | 3 | +33,746.50 | 6,736.15 | +27,010.35 |
| 2026-09-04 | 5 | -8,296.50 | 8,787.75 | -17,084.25 |

The sample contains 373 signals: 320 HOLD, 44 ENTER, five EXIT_REVERSAL_WARNING and four REVERSE. There are 24 engine-error events. Intent counts are not fill counts; investigate unmatched entry intents rather than counting all signals as trades.

## 4. Confirmed implementation findings and proposed fixes

### P0-A: Paper/live strategy mismatch and hidden directional exposure

**Evidence:** `src/website/backend/app/engine.py`, `TradingEngine._open`, adds `nearest_nifty_future(...)` only when `broker.mode == 'PAPER'`. The direction of that future matches the model. A bullish put credit spread plus a long future increases directional exposure; the future is not the spread's protective hedge.

**Implementation:** define explicit strategy identities such as `credit_spread`, `directional_future`, and `spread_plus_future`. Use one strategy leg builder for replay, paper and live modes; execution transport alone should differ. Store strategy/configuration version, leg quantities, estimated aggregate delta, notional and margin. Show separate leg and combined P&L in the UI. Do not silently remove historical legs or rewrite their performance.

**Verification:** compare all three variants at fixed risk and at fixed notional; do not compare unequal lots as though equivalent. Assert paper/live leg-plan parity for the same strategy. Treat combined futures risk separately from the spread's bounded maximum loss.

### P0-B: Recorded quote is not a verified execution

**Evidence:** `app/broker.py`, `ExecutionBroker.execute`, fills immediately at a supplied quote/LTP. `_historical_prices` falls back to the last minute close in a ten-minute query without recording its age as execution evidence. `LiveExecutionBroker.execute` returns the order ID and quote after submission, without reconciling actual fills.

**Implementation:** retain quote source, exchange timestamp, receipt timestamp, decision timestamp and actual fill timestamp. Simulate buys at available ask and sells at bid, subject to spread, size, latency and liquidity limits. Reject stale or missing prices for new entries. If a historical mark is needed for display, label it a mark, not an executable fill. For live execution, reconcile status, filled quantity and average fill price; handle rejection, partial fills and cancellation before updating a completed position.

Kite distinguishes last traded price from order execution information and exposes executed average price and trades. An order acknowledgment is not a fill. See [market quotes](https://kite.trade/docs/connect/v3/market-quotes/) and [order lifecycle documentation](https://kite.trade/docs/connect/v3/orders/).

**Verification:** deterministic stale-price, wide-spread, partial-fill, rejection and out-of-order-update cases; stress costs with conservative slippage. Existing ledger reconciliation does not validate original fill realism.

### P0-C: Signal persistence can suppress execution recovery

**Evidence:** `engine.py` persists a signal before closing/opening positions. The scheduler uses `repository.has_signal` to avoid processing an existing checkpoint. A subsequent execution error can leave a completed-looking checkpoint without completed execution. Multi-leg opening/closing also has failure windows; the opening compensation covers a short-leg failure after the hedge but not every later leg/persistence failure.

**Implementation:** introduce a durable execution intent with explicit `PENDING`, `PARTIAL`, `FILLED`, `FAILED` and reconciled states. Key it by underlying, checkpoint and strategy version. Persist broker order IDs and each leg's status. Recover unresolved intents on restart; do not blindly resend orders. Keep signal generation idempotency separate from execution completion. Add unique active-position constraints where appropriate and concurrency-safe transitions. Broker operations cannot be made atomic just by wrapping SQL in a transaction.

**Verification:** inject failure after each leg and before/after repository writes; restart and prove no duplicate orders or untracked positions. Reconcile the 44 ENTER intents and four REVERSE intents against the 24 opened trades and error events, with reasons.

### P0-D: Order-flow gating couples exit and new-entry permission

**Evidence:** in `engine.py`, an order-flow rejection can turn `REVERSE` into `WAIT_ORDER_FLOW`; the subsequent early return leaves the old position open. `EXIT_REVERSAL_WARNING` follows a separate path. The gate therefore does not exclusively filter the new entry.

**Implementation:** return a structured decision with independent `exit_action` and `entry_action`. Protective exit permission must survive a denied replacement trade. A rejected new direction should leave the system flat if the old position is invalidated. Record both reasons separately; do not describe a rejected reverse as a harmless hold.

**Verification:** an invalidated UP position plus a blocked DOWN entry closes UP and stays flat; stale flow blocks a new entry but never a required risk exit; a valid existing position remains held when only a discretionary new entry is rejected.

### P1-A: Flat state forces entry without an explicit after-cost edge gate

**Evidence:** `position_action(None, direction)` returns ENTER. `models/position.py` accepts UP/DOWN only. The inspected NIFTY manifest has `use_abstention: false`; reversal thresholds constrain changes of direction, not initial entry quality. Walk-forward code supports abstention, but that capability is not an end-to-end live flat-state policy here.

**Implementation:** make FLAT/ABSTAIN first-class operational outcomes. Require calibrated expected net payoff, sufficient time to the mandatory exit, acceptable spread/liquidity and available risk budget. Keep raw prediction distinct from selected action. A direction probability alone cannot establish option-spread expectancy; incorporate move magnitude, volatility, payoff shape and costs.

**Verification:** compare always-enter against abstention at matched risk, including coverage, after-cost expectancy and opportunity cost. Tune only on training/inner-validation blocks. Do not invent a universal probability cutoff from these 24 trades.

### P1-B: Exit rules need risk-aware validation, not blanket removal

**Evidence:** `app/reversal_policy.py` uses two consecutive strong opposing signals (confidence 0.56) and a 0.15% adverse underlying move from entry to choose reverse versus reduce-to-flat. The engine operates on 15-minute checkpoints. These rules do not price the next trade's costs. No explicit portfolio daily-loss budget or per-trade loss-budget enforcement was found in the reviewed app execution path.

**Implementation:** separate emergency risk exits, structural invalidation, model reversal and session closure. Add a portfolio risk service for estimated open-position liquidation P&L, daily loss limits, margin/notional limits and joint NIFTY/SENSEX exposure. Evaluate hysteresis, minimum hold and re-entry cooldown only for discretionary churn; never delay emergency exits. Test ATR/volatility-scaled adverse movement instead of assuming a fixed 15 bps fits every regime. Persist MFE/MAE and net marked P&L at decisions.

**Verification:** compare current exits, risk-only exits, structural exits and cost-aware reversals on identical paths. Measure loss tails and drawdown as well as saved charges. Avoid selecting a stop level that merely removes the observed worst day.

### P1-C: FPI sizing is explicitly contrarian

**Evidence:** `experiments/fpi_futures.py::contrarian_cash_weight` scales to 1.5x when signed cash z-score is below -0.5 and to 0.5x above +0.5. With base lots two, current NIFTY overlay examples use three lots for strong divergence and one for confirmation. Eight divergence trades total INR -21,848.44 net; this small, uneven sample does not establish the overlay's causal effect.

**Implementation:** expose contrarian versus confirming intent clearly. Compare overlay-off, current contrarian and confirming policies at equal risk. Recompute charges from rescaled legs: fixed brokerage means multiplying net P&L by a lot ratio is not exact. Persist the FPI information-availability timestamp in addition to session date; retain the existing prior-session freshness checks. Version calendars rather than relying indefinitely on a hard-coded 2026 holiday set.

**Verification:** check publication timing, missing/stale data, holidays and sizing rounding. FPI daily context is not a substitute for contemporaneous order-book pressure. Keep futures basis, participant positioning and cash-flow effects distinct in ablations.

### P1-D: Cost model must be effective-dated and shared with research

**Evidence:** `app/charges.py` uses hard-coded rate constants. `experiments/fpi_futures.py` defaults to a two-basis-point round-trip cost, while the current futures sell-side STT alone is five basis points of traded value. The costs and economic horizons of those experiments are therefore not directly interchangeable with the paper ledger.

The code's futures STT rate of 0.0005 and option sale rate of 0.0015 match the rates effective from April 2026; high futures charges should not automatically be called a tax-calculation bug. See the [NSE STT circular](https://nsearchives.nseindia.com/content/circulars/FATAX73524.pdf). Other exchange charges, historical dates and contract-note rounding still require reconciliation against the [broker schedule](https://zerodha.com/charges/).

**Implementation:** one effective-dated instrument/exchange/side cost service for replay, marking and execution. Store schedule version and cost components per leg. Calculate breakeven expected movement before entry/reversal; include spread and slippage separately from statutory charges. Use actual traded contracts, not unadjusted continuous-futures points, to validate execution results.

### P1-E: Feature freshness and reproducibility

**Evidence:** `app/prediction.py::_feature_row` selects the latest eligible feature row no later than checkpoint minus one three-minute bar. It checks the session but does not require the exact expected latest bar. `DirectionalSignal` carries `feature_timestamp`, while the inspected signal persistence does not retain that field.

**Implementation:** validate expected completed-bar timestamp and clock skew; distinguish market closure from a missing bar. Persist feature/data/model hashes, training cutoff, manifest version, configuration snapshot, feature timestamp and decision timestamp. Record catch-up checkpoints separately from actual execution times so a delayed decision is not backdated as a historical fill.

**Verification:** missing latest bar, delayed data, late scheduler and revised historical inputs. Reproduce a saved decision from an immutable input snapshot. Current source is not guaranteed to be the exact version used by every historical trade.

## 5. Order flow: how to use the existing integration safely

### 5.1 Available evidence

The database contains 682,842 raw ticks, 71,855 indicator snapshots and 71,855 shadow decisions. Shadow decisions cover September 1-4, with one instrument per session in the inspected aggregates. These are highly correlated observations, not 71,855 independent trades. The tick total may include broader capture scope than the snapshot series.

Only September 1 has a recorded replay run: 18,142 processed observations, 1,493 zone events, 442 actionable decisions and 438 evaluated decisions. Of those, 258 have positive signed three-minute price returns: 58.9%.

| Setup | Evaluated decisions | Three-minute hit rate | Mean signed return, bps |
| --- | ---: | ---: | ---: |
| SUPPORT_BOUNCE | 35 | 82.9% | 2.47 |
| SUPPORT_BREAKDOWN | 179 | 58.1% | 0.83 |
| RESISTANCE_BREAKOUT | 144 | 52.8% | 0.42 |
| RESISTANCE_REJECTION | 80 | 61.3% | 1.11 |

These returns are gross underlying-price movements, not executable derivative profits. The replay measures sign after three minutes, not stop/target first-touch success. Actionable observations can recur every 30 seconds, so three-minute outcomes overlap. The apparent bounce advantage has only 35 observations from one day and should not be selected as a production rule.

### 5.2 Integration gaps

- `order_flow_filter_enabled` is currently false. Current settings do not prove the flag's historical state, but there are no WAIT_ORDER_FLOW actions in the inspected signal totals.
- `OrderFlowStore.replay_readiness` requires ten distinct sessions and 100 evaluated decisions. Current evidence fails the session requirement. Readiness checks sample volume, not net profitability, calibration or out-of-sample performance.
- `decision_before` selects the latest decision within 90 seconds, but has no instrument-token, underlying, expiry, source or policy-version predicate. One instrument per session does not make this future-proof when contracts or streams multiply.
- Replay and operational decisions share storage. The lookup needs explicit live/replay provenance and information-availability timestamps to prevent retrospectively rebuilt decisions from masquerading as contemporaneous evidence.
- Replay processes a sequential file and uses timestamp bisection for future outcomes. Validate monotonic timestamps, session boundaries, duplicates and a single instrument before processing; do not mix contracts into one indicator state.
- The footprint path labels aggressor side as estimated. Preserve that label; inferred buy/sell volume and sampled depth are not an exchange-certified sequence of aggressor trades.

### 5.3 Recommended architecture

1. Keep the current directional model as the higher-horizon context during initial experiments.
2. Build an immutable flow feature snapshot keyed by underlying, instrument token, expiry, exchange time, availability time and policy version.
3. Map the signal's underlying to the correct liquid futures contract for that session, accounting for expiry and roll. Do not apply a NIFTY snapshot to SENSEX.
4. Evaluate multi-observation pressure persistence, depth/spread quality, price response, zone location and failed-auction/rejection evidence. Treat raw imbalance alone as insufficient.
5. Initially use flow for entry timing or abstention, not an automatic reversal of the strategic direction. A 30-second flow change and a 15-minute/rest-of-session model have different horizons.
6. Keep protective exits independent. Missing, stale or conflicting flow may deny an entry, not suppress a risk exit.
7. Store shadow decisions for every candidate, including rejected candidates, so filter benefit is measurable rather than inferred from selected winners.

### 5.4 Experiments before activation

Compare baseline, flow entry gate, flow execution timing, and flow risk-reduction variants. Hold strategy legs, risk allocation, FPI policy and cost schedule fixed. Align each snapshot strictly before the decision and require that it was actually available then. Deduplicate events by independent opportunity and evaluate at session level.

Measure 3/5/15/30-minute price response plus actual selected-contract P&L until strategy exit. Reconstruct bid/ask fills, costs, rejected opportunities and coverage. Use more independently captured/replayed sessions across trend, range, high/low volatility and expiry conditions. Ten sessions is only the existing plumbing threshold, not sufficient proof of edge. Do not run the existing replay command against production just for analysis: its default replacement path deletes/rebuilds session-derived tables.

## 6. Model evaluation and research improvements

The existing `evaluation/walk_forward.py` already separates sessions chronologically and tunes decision/abstention thresholds inside training-only blocks. Preserve that useful foundation. Its threshold objectives emphasize classification performance; profitable trading also depends on payoff asymmetry, frequency and costs.

Required evaluation pipeline:

1. Freeze raw data, training cutoff, features, model artifact, strategy legs, policy and fee schedule.
2. Generate predictions only from completed, available inputs. Keep label/future-outcome columns out of features.
3. Replay the same state machine used by paper execution, including FLAT, partial/rejected orders, exits and subsequent re-entry.
4. Mark actual contracts through time and aggregate simultaneous NIFTY/SENSEX risk.
5. Select thresholds on inner chronological validation using after-cost expectancy constrained by coverage, drawdown and turnover.
6. Evaluate once on untouched outer chronological blocks. Purge observations whose label windows cross split boundaries; use session grouping where labels end within a session, with a gap for longer-horizon labels.
7. Estimate uncertainty using session/block resampling, not independent tick assumptions. Report confidence intervals, sample sizes and regime breakdowns.
8. Maintain a register of all attempted variants. Many parameter trials can produce impressive in-sample results by chance; see [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Report net expectancy per trade and per session, profit factor, average win/loss, turnover, cost drag, intraday and end-of-day drawdown, tail loss, exposure, fill quality and coverage. Probability calibration should include reliability bins, Brier/log loss and sufficient sample disclosure. Win rate alone is not a promotion criterion.

## 7. Phased implementation backlog

### Phase A: Establish trustworthy accounting and lineage

- Add explicit strategy and version identities; preserve old ledger records.
- Persist actual exit reason on the trade/execution record instead of parsing event messages.
- Add decision, feature, quote and execution timestamps plus source/model/configuration hashes.
- Add execution-intent/leg states and reconciliation diagnostics.
- Expose a credential-free database identity/configuration-source indicator to prevent reviewing or operating the wrong database.
- Add tests in the existing trade-ledger/website test areas for leg reconciliation, partial fills and restart recovery.

Done when every trade can be traced to a reproducible decision and reconciled execution, unmatched intents have explanations, and paper/live strategy leg plans agree.

### Phase B: Make risk and costs enforceable

- Share effective-dated cost calculation across research, marks and execution.
- Add realistic paper fills and quote freshness rejection.
- Separate required exits from replacement-entry gates.
- Add independent portfolio/per-trade risk budgets and correlation-aware exposure limits.
- Display gross, charges, estimated slippage and net results by strategy/leg.

Done when fault-injection and risk tests pass and the baseline can be replayed with conservative executable prices. Choose risk limits explicitly against account capital; no arbitrary capital-based numbers are assumed in this report.

### Phase C: Reduce unproductive trading through controlled experiments

- Compare spread-only, future-only and combined strategies at matched risk.
- Add first-class abstention and cost-aware entry/reversal decisions.
- Compare current versus alternative exit/hysteresis/cooldown policies without weakening emergency exits.
- Compare FPI sizing off/current/confirming, recalculating costs and risk.
- Add calibration and regime/time-of-day evaluation without hand-selecting the winning slices.

Done when a predeclared candidate improves independent after-cost outcomes and risk metrics across multiple blocks, with sufficient coverage and uncertainty reported. A failed experiment remains a documented result.

### Phase D: Validate order flow in shadow mode

- Add instrument/expiry/source/version-scoped lookup and availability timestamps.
- Separate live capture from replay namespaces or enforce equivalent provenance controls.
- Replay additional immutable captures in an isolated analysis database.
- Add chronology, overlap, stale-feed, wrong-contract and gate/exit-independence tests.
- Run paired baseline/flow comparisons with independent session-level uncertainty.

Done when flow has measurable incremental value after costs and rejection opportunity cost, not merely a higher tick-level hit rate.

### Phase E: Controlled paper rollout and promotion gate

- Freeze a candidate and run champion/challenger paper books using identical market inputs and risk budgets.
- Monitor fill age, stale feeds, unmatched orders, model drift, turnover, net expectancy and loss-limit behavior.
- Require sustained out-of-sample evidence under realistic costs, no unresolved reconciliation defects, paper/live strategy parity and explicit approval before live rollout.
- Retain a rollback configuration and a kill switch. Do not automatically increase size after a few winning sessions.

## 8. Reproducible audit queries

Use a read-only connection to the verified database. Do not instantiate application repositories for an audit if their constructors apply migrations. Do not put a DSN in scripts or reports. For a repeat audit, use a read-only repeatable-read transaction so all aggregates share one snapshot; this review used sequential read-only checks and is not a formally frozen database export.

```sql
-- Recorded closed-paper performance.
SELECT underlying, COUNT(*) AS trades,
       SUM(gross_pnl) AS gross, SUM(total_charges) AS charges,
       SUM(net_pnl) AS net,
       COUNT(*) FILTER (WHERE net_pnl > 0) AS net_winners
FROM public.trades
WHERE mode = 'PAPER' AND status = 'CLOSED'
GROUP BY underlying;

-- Reconstruct attribution from fills without changing the ledger.
SELECT t.underlying, l.role, COUNT(*) AS legs,
       SUM((l.exit_price-l.entry_price)*l.quantity*
           CASE WHEN l.entry_side='BUY' THEN 1 ELSE -1 END) AS gross,
       SUM(COALESCE((l.entry_charges->>'total')::numeric,0) +
           COALESCE((l.exit_charges->>'total')::numeric,0)) AS charges
FROM public.trades t JOIN public.trade_legs l ON l.trade_id=t.id
WHERE t.mode='PAPER' AND t.status='CLOSED'
GROUP BY t.underlying,l.role;

-- Join close evidence; do not mistake entry rationale for exit rationale.
SELECT t.id,t.underlying,t.exit_time,t.net_pnl,e.message
FROM public.trades t JOIN public.events e ON e.payload->>'id'=t.id::text
WHERE t.mode='PAPER' AND e.kind='trade_closed';

SELECT session_date,source,ticks_processed,events_evaluated,metrics
FROM order_flow.replay_runs ORDER BY session_date;
```

Before exporting row-level evidence, remove account/session credentials and sensitive event payload fields. A future audit exporter should include row counts, maximum timestamps, source revision and a manifest checksum.

## 9. Separate TradeLens EOD-pattern observations

These are not explanations for the NIFTY/SENSEX paper losses above. The TradeLens database inspected separately had no research runs, entries or outcomes, and only three securities with adjusted/feature history. Benchmark, sector membership and relative-strength coverage were incomplete.

The reviewed TradeLens critical paths also warrant separate correctness work:

- `src/backend/pattern_engine/breakout_detectors.py`: historical trigger selection and narrow failure handling can preserve stale triggered states. Persist lifecycle transitions across intervening bars; distinguish an old breakout from a fresh actionable setup.
- `src/backend/pattern_engine/research.py`: reject any entry dated before the candidate and its filtering/ranking evidence were knowable. A recorded historical breakout date is not permission to enter retroactively using later features.
- Preserve per-security adjustment/feature lineage during replay; mutable current features must not be paired with unrelated historical adjustment versions.
- Treat unavailable relative strength or sector context as missing coverage, not silently equivalent to weak evidence. Separate evidence availability from setup quality.
- Add lifecycle, no-lookahead and version-consistency regression cases before using EOD pattern outcomes for trading claims.

The TradeLens backend test run completed with 172 tests, one skipped live-NSE test (171 passed). That does not validate MarketPlaygroud's profitability or substitute for its execution/replay tests. No full MarketPlaygroud test suite, live-order exercise or new out-of-sample strategy experiment was performed for this report.

## 10. Recommended decision

Start with Phases A and B. Then test whether the model has sufficient after-cost edge in each explicitly defined strategy before optimizing exits or adding order-flow complexity. Keep the current ledger immutable and retain the loss periods in all evaluations. The most useful next deliverable is a reproducible, risk-normalized replay comparison, not a threshold chosen to make these nine sessions look better.
