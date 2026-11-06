# Overview highest-ranked setup qualification

Status: implemented and tested in source, 2026-11-01. Restart the backend to
load the new query and policy in an existing application process.
Policy identifier: `overview-qualified-v1`.

## Problem and existing behavior

Overview previously listed every eligible equity after pagination. Its original
six-card limit was a presentation limit, not a qualification rule. The current
candidate query requires EQ securities, daily SETUP patterns, nonterminal READY,
TRIGGERED or CONFIRMED state, and the latest available security evaluation at or
before the Overview evidence date. It keeps one representative per ISIN.

The representative preference is lifecycle state, pattern class, setup score,
detection date and stable ID. It does not select the maximum best-fit score
across all patterns for an equity. Preserve that established behavior in this
change; changing representative selection is a separate ranking decision.

Best fit is already calculated as:

`0.75 × setup score + 0.10 × context score + 0.15 × liquidity score`.

Peer percentiles are calculated within lifecycle state. Existing display tiers
are LEADING at percentile 95+, STRONG at 80+, QUALIFIED at 50+, and DEVELOPING
below 50. Neither a tier nor a score is a probability or historical outcome.

## Accepted qualification: every condition must pass

| Condition | Rule | Reason |
| --- | --- | --- |
| Existing eligibility | Preserve the current candidate universe and one representative per ISIN | Avoid changing the detector or screener universe |
| Current evidence | Pattern evaluation date equals Overview `dataAsOf`; required prices come from that session and matching calculation versions | Do not feature a security's older retained snapshot as current |
| Strong peer position | Best-fit percentile within its lifecycle state >= 80 | Reuse the existing STRONG/LEADING distinction |
| Absolute best-fit floor | Best-fit score >= 70/100 | A weak cohort must not qualify a weak result solely by relative rank |
| Geometry floor | Pattern quality >= 70/100 | Require acceptable pattern geometry independently of context/liquidity |
| Context floor | Context score >= 40/100 | Exclude the range already labelled weak by the explanation service |
| Liquidity | Persisted liquidity score = 100, with available scoring lineage | Require all configured liquidity checks, rather than three of four |
| Essential levels | Adjusted close, pivot and invalidation are present, finite and positive; adjusted close > invalidation | Exclude missing essential evidence and snapshots already beyond their risk boundary |

The 70-point best-fit and generic quality floors are accepted Overview product
policy, not existing universal detector rules or backtest-calibrated thresholds.
Keep them configurable and versioned separately from detector configuration.
The percentile boundary and context interpretation reuse current application
semantics. Liquidity 75 is currently a preferred-profile explanation threshold;
it represents only three of four checks, so this shortlist deliberately uses 100.
The existing liquidity defaults are price >= INR 20, history >= 250 sessions,
20-session median traded value >= INR 20,000,000, and configured median volume
>= 0. Read the versioned engine configuration; do not duplicate these numeric
liquidity thresholds in SQL or React.

Do not require invalidation < pivot: current breakout snapshots legitimately
use the pivot itself as invalidation. Do not invent missing prices or scores.

## Cohort, ordering and pagination

1. Resolve the Overview evidence date and existing eligible representatives.
2. Compute the existing best-fit scores and lifecycle peer percentiles over
   that complete candidate cohort. Score/quality/context/health qualification
   must not shrink the cohort before percentiles are calculated.
3. Apply every qualification rule in the server query.
4. Count qualified results, then sort and apply the cursor/page limit.
5. Load six qualified results per page, preserving the initial `dataAsOf`.

Equal best-fit scores receive the same peer percentile and qualification result;
stable IDs only resolve display ordering. Specify a singleton percentile of 100
consistently in PostgreSQL and the in-memory implementation. The current SQL
PERCENT_RANK gives a singleton 0 while the fake gives it 100; fix this mismatch
before relying on the boundary. Retain PERCENT_RANK tie semantics otherwise.
Evaluate the unrounded percentile at the boundary; round only for display.

Retain the current best-fit descending list order, but label each card's peer
rank with its lifecycle state. Do not present the mixed-state list position as
a universal lifecycle peer rank, or use confidence to override qualification.

Do not fill an empty/short list with nonqualifying results. An empty result says
that no setups meet this policy for the stated evidence date. Load more must
never fall through to the general setup universe. Keep the existing screener
link for broader exploration.

## Database review

Read-only inspection performed on 2026-11-01. Market evidence date: 2026-10-30.
Counts are one representative per equity, not raw pattern-instance totals.

| Selection using current peer percentiles | Equities |
| --- | ---: |
| Existing eligible Overview universe | 278 |
| Peer percentile >= 80 only | 58 |
| Also best fit >= 70 | 36 |
| Also quality >= 70 | 14 |
| Also current evidence, full liquidity and essential risk checks | 14 |
| Also context >= 40: proposed shortlist | 13 |

The projected shortlist contains 3 READY, 1 TRIGGERED and 9 CONFIRMED equities.
It would load as 6 + 6 + 1 cards. Candidate symbols in existing display order:
ADANIPORTS, NITINSPIN, SSWL, SHREEJISPG, MANAKCOAT, SHREEPUSHK, KOLTEPATIL,
KOTAKBANK, CEIGALL, ETERNAL, SATIN, APOLLO, NAZARA.

The 278-candidate universe includes one older 2026-09-11 snapshot and four
adjusted closes at/below invalidation. These are not grounds to rewrite lifecycle
history in a read endpoint; exclude them from the featured shortlist and retain
their underlying evidence for investigation.

Relative-strength percentile is absent from the current setup query results
for all 278 candidates, and maturity is absent for 258. The security fingerprint
has a separate computed-RS fallback that this query does not currently use.
Do not silently introduce that fallback into qualification or label these rows
fully evidenced. Display named missing-evidence cautions; a universal 100%
completeness or RS requirement would currently remove every candidate. Retain
existing confidence reduction for missing evidence. Investigate lineage and
family-specific maturity availability separately.

Four of the proposed 13 results exceed the existing 8% extension caution. Keep
that caution visible rather than silently turning a ranking shortlist into a
new-entry screen. A future entry-proximity filter needs its own explicit rule.

This snapshot checks selectivity and operability. It does not establish future
performance, win probability, or an optimal trading threshold.

## Implementation contract and checks

Implemented in `pattern_engine/overview_qualification.py`,
`configuration/overview.toml`, and `repositories/overview_queries.py`. The policy
configuration has a content hash in response metadata, independently of engine
configuration. The PostgreSQL and in-memory implementations pass the opt-in
read-only database parity check, including all pages and an exhausted cursor.
On the reviewed database, the new query returns 13 of 278 candidates; one
read-only `EXPLAIN ANALYZE` measured 87 ms execution and 48 ms planning. These
measurements describe this local snapshot, not a production performance SLA.

Run deterministic checks with `python -m unittest test_overview_qualification`
from `src/backend`. Set `TRADELENS_RUN_OVERVIEW_DB_TESTS=1` to explicitly opt in
to the database parity check. It does not modify market records or migrations.

- Put versioned qualification rules in a focused pattern-engine module and
  apply them in repository SQL, after peer ranking and before pagination.
  The existing fast query joins features after LIMIT; qualification requiring
  close/date/lineage must move those bounded evidence joins before LIMIT.
- Preserve existing `/api/setups` behavior and all detector/scorer formulas.
  No new table or market-data migration is needed for a derived shortlist.
- Extend Overview with qualification metadata: policy version, thresholds,
  candidate count, qualified count, peer scope and evidence date. Each returned
  setup carries the policy version and actual values explaining its inclusion.
  Never derive eligibility in React.
- Show a brief rule summary, "Showing N of M qualified setups", and a Load more
  button for qualified results only. Retain stale/partial evidence labels.
- Add offline boundary, missing-input, liquidity-75-versus-100, stale-date,
  at/below-invalidation, lifecycle, tie and singleton tests; prove qualification
  precedes LIMIT and does not recompute peer ranks inside the qualified subset.
- Test PostgreSQL/in-memory parity, cursor exhaustion, empty shortlist, retries,
  unmount cancellation and initial-date preservation. Run the complete backend
  suite, frontend tests and build. Verify the new SQL on the read-only database
  and inspect its query plan before release.

Source locations: `pattern_engine/query_service.py` (`overview`, `_best_fit`,
`_fit_tier`), `repositories/pattern_queries.py` (`list_setups`,
`_list_setups_pattern_ranked`), `pattern_engine/decision_intelligence.py`,
`pattern_engine/scoring.py`, `configuration/pattern_engine.toml`, and canonical
specification sections 123–129. Paths are relative to `src/backend` except the
specification under `src/doc`.
