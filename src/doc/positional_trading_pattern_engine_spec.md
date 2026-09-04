# Positional Trading Technical Pattern Engine
## Final Pattern Taxonomy, Mathematical Definitions, Measurements, Scoring, Lifecycle, and Implementation Specification

**Version:** 1.0  
**Scope:** Indian equities, end-of-day positional trading  
**Primary data:** Corporate-action-adjusted daily OHLCV, with optional delivery data and benchmark/index data  
**Purpose:** Canonical implementation specification for the technical-pattern detection and scoring engine

---

# 1. Objective

The platform is not intended to be a generic stock screener or a replica of BananaPatterns.

Its core purpose is:

> **Continuously classify every stock by technical structure, detect emerging positional setups, measure the geometry and quality of those setups, track their lifecycle, and expose the technical evidence behind every detection.**

A pattern is therefore not only a label such as `VCP` or `Breakout`.

Every detected pattern instance must have:

- a pattern class,
- a pattern type,
- an optional variant,
- a start date,
- a detection date,
- a current lifecycle state,
- a quality score,
- a maturity score,
- technical measurements,
- pivot/support/invalidation levels where applicable,
- supporting technical signals,
- and an explicit invalidation condition.

The final platform should answer:

1. What technical structure is present?
2. What pattern is forming?
3. How strong is the pattern?
4. How mature is it?
5. Where is the trigger or pivot?
6. What would invalidate it?
7. What supporting technical conditions are present?
8. How has the pattern evolved over time?
9. How did similar setups historically behave?

---

# 2. Design Principles

## 2.1 Deterministic first

The first version of the engine should use deterministic, explainable rules.

The system should be able to explain every detection numerically.

Example:

```text
Pattern              BASE-VCP
Variant              VCP-3C
State                READY

Contractions         14.2% -> 8.5% -> 4.1%
ATR compression      0.58
Volume compression   0.51
Distance to pivot    1.7%
Pattern quality      92
Maturity             88
```

Machine learning may later optimize thresholds or rank setups, but it should not replace the deterministic pattern definition.

---

## 2.2 Pattern geometry and market context are separate

The pattern detector should answer:

> Does this pattern exist?

The context engine should answer:

> Is this pattern occurring in a favorable environment?

For example, the VCP detector should not internally require a strong market regime.

Instead:

```text
Pattern Detector
    |
    +-- Pattern geometry
    +-- Pivot
    +-- Quality
    +-- Maturity
    +-- State

Context Engine
    |
    +-- Market regime
    +-- Sector strength
    +-- Trend strength
    +-- Relative strength
    +-- Volume context
    +-- Liquidity

Setup Scoring Engine
    |
    +-- combines both
```

This separation makes the system easier to test and allows later historical analysis of questions such as:

> Does `BASE-VCP` work better when `RS6M > 90` and `TREND-S2` is active?

---

## 2.3 All thresholds are configurable defaults

Every numeric threshold in this document should be implemented as configuration, not as hard-coded business logic.

Examples:

```text
VCP_MIN_DURATION
VCP_MAX_DURATION
VCP_MAX_DEPTH
BREAKOUT_MIN_BUFFER
BREAKOUT_MAX_BUFFER
EMA20_PULLBACK_MAX_DEPTH
```

The values in this document are initial defaults.

Backtesting can later optimize them.

---

# 3. Final Pattern Classification

The engine uses seven top-level technical classes.

| Class | Purpose |
|---|---|
| `TREND` | Structural direction and trend regime |
| `BASE` | Consolidation and accumulation structures |
| `BREAKOUT` | Transition above established resistance |
| `PULLBACK` | Continuation/re-entry structures inside a trend |
| `COMPRESSION` | Volatility and range contraction |
| `MOMENTUM` | Absolute and relative strength expansion |
| `FAILURE` | Breakdown, deterioration, and setup invalidation |

Volume is treated as a cross-cutting measurement layer rather than a standalone top-level class.

---

# 4. Final Pattern Inventory

## 4.1 Primary positional setups

These are the primary actionable setup families.

```text
BASE-VCP
BASE-FLAT
BASE-52WH

BRK-RANGE
BRK-52WH
BRK-ATH
BRK-MULTIY

PB-BRKRET
PB-EMA20
PB-SMA50
```

---

## 4.2 Supporting patterns

These add technical evidence but are generally not primary setups on their own.

```text
TREND-HHHL
TREND-S2
TREND-MA

BASE-TIGHT

COMP-NR7
COMP-IB
COMP-ATR
COMP-RANGE

MOM-ACC
MOM-RSL
MOM-RSB

VOL-DRY
VOL-EXP
```

---

## 4.3 Failure patterns

```text
FAIL-BRK
FAIL-BASE
FAIL-EMA20
FAIL-SMA50
FAIL-STRUCT
```

---

# 5. Pattern Identifier Convention

Pattern identifiers should be stable and machine-friendly.

## 5.1 VCP variants

```text
VCP-2C
VCP-3C
VCP-4C
VCP-5C
```

where `C` means contraction count.

---

## 5.2 Moving-average pullbacks

```text
PB-EMA20
PB-SMA50-T1
PB-SMA50-T2
PB-SMA50-T3+
```

where `T1`, `T2`, etc. indicate the distinct touch number of the 50-day moving average.

---

## 5.3 Multi-year breakout variants

```text
BRK-2Y
BRK-3Y
BRK-5Y
```

---

## 5.4 Compression variants

```text
COMP-IB1
COMP-IB2
COMP-IB3
```

for one, two, or three consecutive inside bars.

---

# 6. Input Data Requirements

Minimum input for pattern detection:

```text
Date
Open
High
Low
Close
Volume
```

Recommended additional data:

```text
DeliverableQuantity
DeliveryPercentage
BenchmarkClose
SectorIndexClose
CorporateActions
```

All price-series pattern analysis should use corporate-action-adjusted historical prices.

---

# 7. Common Mathematical Foundation

All pattern detectors should use the same standardized feature layer.

---

# 8. True Range

For session \(t\):

\[
TR_t =
\max
\left(
H_t-L_t,
|H_t-C_{t-1}|,
|L_t-C_{t-1}|
\right)
\]

Where:

- \(H_t\) = current high
- \(L_t\) = current low
- \(C_{t-1}\) = previous close

---

# 9. Average True Range

Use Wilder ATR by default.

\[
ATR_n(t)
=
\frac{
ATR_n(t-1)(n-1) + TR_t
}{n}
\]

Recommended values:

```text
ATR5
ATR10
ATR14
ATR20
ATR50
```

The default general-purpose ATR is:

```text
ATR14
```

---

# 10. Normalized ATR

Raw ATR cannot be directly compared across stocks with different prices.

Use:

\[
NATR_n =
\frac{ATR_n}{Close} \times 100
\]

Example:

```text
Close = 500
ATR14 = 12

NATR14 = 12 / 500 * 100
        = 2.4%
```

---

# 11. Moving Averages

Calculate:

```text
EMA10
EMA20

SMA50
SMA100
SMA200
```

EMA:

\[
EMA_t =
\alpha C_t + (1-\alpha)EMA_{t-1}
\]

where:

\[
\alpha = \frac{2}{n+1}
\]

---

# 12. Moving Average Slope

Slope should be normalized.

For a 20-session SMA50 slope:

\[
SMA50Slope_{20} =
\frac{
SMA50_t - SMA50_{t-20}
}{
SMA50_{t-20}
}
\]

Optional daily-normalized form:

\[
DailySlope =
\frac{SMA50Slope_{20}}{20}
\]

Use normalized percentage slope rather than raw price slope.

---

# 13. Rolling Price Range

For lookback \(n\):

\[
Range_n =
\frac{
HighestHigh_n - LowestLow_n
}{
HighestHigh_n
}
\times 100
\]

Recommended:

```text
Range5
Range10
Range20
Range50
```

---

# 14. Volume Normalization

Volume is often distorted by one or two large spikes.

Use rolling medians for structural pattern analysis.

```text
Vol5  = Median(Volume over last 5 sessions)
Vol10 = Median(Volume over last 10 sessions)
Vol20 = Median(Volume over last 20 sessions)
Vol50 = Median(Volume over last 50 sessions)
```

---

# 15. Current Volume Ratio

\[
VolumeRatio20 =
\frac{Volume_t}{MedianVolume_{20}}
\]

Interpretation:

```text
< 0.70     Low
0.70-1.00  Below normal
1.00-1.30  Normal
1.30-2.00  Strong expansion
> 2.00     Very strong expansion
```

---

# 16. Volume Contraction

\[
VolumeContraction =
\frac{MedianVolume_5}{MedianVolume_{50}}
\]

Interpretation:

```text
> 0.90      Weak contraction
0.75-0.90   Moderate
0.55-0.75   Strong
< 0.55      Very strong
```

---

# 17. Close Location Value

Close Location Value measures where the close occurred inside the day's range.

\[
CLV =
\frac{Close-Low}{High-Low}
\]

If `High == Low`, define `CLV = 0.5`.

Interpretation:

```text
0.00    close at low
0.25    lower quarter
0.50    midpoint
0.75    upper quarter
1.00    close at high
```

For strong breakout candles:

```text
CLV >= 0.70
```

Excellent:

```text
CLV >= 0.85
```

---

# 18. Swing Point Engine

The swing engine is foundational.

VCPs, trend structures, pivots, support, resistance, and breakout retests depend on it.

---

## 18.1 Raw swing high

A swing high at bar \(t\) exists if:

\[
High_t =
\max(
High_{t-3},...,High_{t+3}
)
\]

Equivalent:

```text
High[t] >= all highs from t-3 to t+3
```

---

## 18.2 Raw swing low

\[
Low_t =
\min(
Low_{t-3},...,Low_{t+3}
)
\]

---

## 18.3 Confirmation delay

A 3-bar-right pivot is only known three sessions later.

Therefore store:

```text
PivotDate
ConfirmationDate
```

with:

```text
ConfirmationDate = PivotDate + 3 trading sessions
```

Backtesting must never use a pivot before its confirmation date.

This avoids look-ahead bias.

---

## 18.4 Minimum meaningful swing

Small oscillations should not create false pivots.

Define:

\[
MinimumSwingPct =
\max(
4\%,
2 \times NATR14
)
\]

Example:

```text
NATR14 = 2.5%

2 * NATR14 = 5%

MinimumSwing = 5%
```

A pivot-to-pivot move smaller than 5% can be ignored in this example.

---

# 19. Resistance Zone Clustering

Resistance should not be modeled as an exact rupee price.

Suppose confirmed swing highs are:

```text
499
502
500
```

They belong to one technical zone.

Define zone tolerance:

\[
ResistanceTolerance =
Clamp(
0.5 \times NATR14,
0.75\%,
2.00\%
)
\]

Cluster swing highs if:

\[
\frac{|High_i - High_j|}{Median(High_i,High_j)}
\le ResistanceTolerance
\]

Pivot price:

\[
Pivot =
Median(clustered\ swing\ highs)
\]

---

# 20. Support Zone Clustering

Use the same tolerance methodology for swing lows.

\[
Support =
Median(clustered\ swing\ lows)
\]

---

# 21. Breakout Buffer

A close a few paise above resistance should not automatically be treated as a breakout.

Define:

\[
BreakoutBuffer =
Clamp(
0.25 \times NATR14,
0.30\%,
1.00\%
)
\]

Example:

```text
NATR14 = 2.4%

0.25 * 2.4% = 0.60%

BreakoutBuffer = 0.60%
```

Breakout confirmation threshold:

\[
Close >
Pivot \times (1 + BreakoutBuffer)
\]

---

# 22. Price Location Measurements

Calculate globally:

```text
DistanceToEMA20
DistanceToSMA50
DistanceToSMA200
DistanceTo52WHigh
DistanceToATH
DistanceToPivot
RangePosition52W
```

Generic percentage distance:

\[
DistancePct =
\frac{Price-Level}{Level}\times100
\]

For distance below a pivot:

\[
DistanceToPivot =
\frac{Pivot-Close}{Close}\times100
\]

---

# 23. 52-Week Range Position

\[
RangePosition52W =
\frac{
Close - Low_{252}
}{
High_{252} - Low_{252}
}
\times100
\]

Interpretation:

```text
0      at 52-week low
50     middle of range
100    at 52-week high
```

---

# 24. Relative Strength Framework

Use a broad benchmark such as NIFTY 500.

For horizon \(n\):

\[
StockReturn_n =
\frac{Close_t}{Close_{t-n}} - 1
\]

\[
BenchmarkReturn_n =
\frac{Benchmark_t}{Benchmark_{t-n}} - 1
\]

\[
ExcessReturn_n =
StockReturn_n - BenchmarkReturn_n
\]

Calculate:

```text
RS1M
RS3M
RS6M
RS12M
```

Rank `ExcessReturn` across the equity universe and convert to percentile:

```text
0-100
```

Example:

```text
RS6M = 96
```

means the stock's six-month relative performance ranks in approximately the top 4% of the monitored universe.

---

# 25. PRIMARY PATTERN: BASE-VCP

VCP stands for Volatility Contraction Pattern.

The detector must identify a sequence of meaningful price contractions whose amplitude progressively decreases.

---

# 26. BASE-VCP Candidate Window

Default base duration:

```text
Minimum: 20 trading sessions
Maximum: 90 trading sessions
```

---

# 27. BASE-VCP Base Depth

\[
BaseDepth =
\frac{
BaseHigh - BaseLow
}{
BaseHigh
}
\times100
\]

Default acceptable range:

```text
8% <= BaseDepth <= 35%
```

Preferred:

```text
10% to 25%
```

---

# 28. BASE-VCP Prior Trend Context

Preferred conditions:

```text
Close > SMA50
SMA50 > SMA200
SMA50Slope > 0
```

These are context factors and should affect quality/context score, not necessarily geometry detection.

---

# 29. VCP Contraction Extraction

Use alternating confirmed swing highs and swing lows.

Example:

```text
SH1 = 500
SL1 = 420

SH2 = 490
SL2 = 446

SH3 = 485
SL3 = 461
```

For contraction \(i\):

\[
C_i =
\frac{
SH_i - SL_i
}{
SH_i
}
\times100
\]

Example:

\[
C_1 = \frac{500-420}{500}=16\%
\]

\[
C_2 = \frac{490-446}{490}=8.98\%
\]

\[
C_3 = \frac{485-461}{485}=4.95\%
\]

---

# 30. VCP Contraction Count

Require:

```text
Minimum: 2
Maximum: 5
```

Variants:

```text
VCP-2C
VCP-3C
VCP-4C
VCP-5C
```

---

# 31. VCP Contraction Progression

Ideal condition:

\[
C_n < C_{n-1}
\]

Preferred strong contraction:

\[
\frac{C_n}{C_{n-1}} \le 0.75
\]

Excellent:

\[
\frac{C_n}{C_{n-1}} \le 0.60
\]

A weak progression may still be accepted if:

\[
C_n \le 0.90 \times C_{n-1}
\]

---

# 32. VCP Final Contraction

Preferred:

```text
LastContraction <= 8%
```

Strong:

```text
<= 6%
```

Excellent:

```text
<= 4%
```

---

# 33. VCP ATR Compression

Compare late-base volatility to early-base volatility.

\[
ATRCompression =
\frac{
Median(ATR10,\ last\ third)
}{
Median(ATR10,\ first\ third)
}
\]

Interpretation:

```text
> 0.90      Weak
0.75-0.90   Moderate
0.55-0.75   Strong
< 0.55      Excellent
```

---

# 34. VCP Volume Compression

\[
VolumeCompression =
\frac{
MedianVolume(last\ 10)
}{
MedianVolume(first\ half\ of\ base)
}
\]

Preferred:

```text
< 0.75
```

Strong:

```text
< 0.60
```

Excellent:

```text
< 0.50
```

---

# 35. VCP Low Progression

Preferred:

```text
SL2 > SL1
SL3 > SL2
...
```

Allow volatility tolerance:

\[
LaterLow \ge PreviousLow - 0.5 \times ATR14
\]

This prevents rejecting technically valid contractions because of minor volatility noise.

---

# 36. VCP Pivot

Use the final contraction swing high or the median of the nearby resistance cluster.

\[
Pivot =
Median(final\ resistance\ cluster)
\]

---

# 37. VCP Distance to Pivot

\[
PivotDistance =
\frac{Pivot-Close}{Close}\times100
\]

---

# 38. VCP State Model

### DETECTED

At least two valid contractions exist.

### FORMING

```text
Maturity < 65
```

### MATURE

```text
Maturity >= 65
```

### READY

Recommended initial rule:

```text
Maturity >= 80
AND PivotDistance <= 3%
AND LastContraction <= 8%
```

### TRIGGERED

```text
Close > Pivot * (1 + BreakoutBuffer)
```

### CONFIRMED

For example:

```text
Two consecutive closes above Pivot
```

or:

```text
One strong breakout close
AND no failure on the next session
```

---

# 39. VCP Invalidation

Invalidate if any of the following occurs:

```text
Close < BaseLow
```

or:

\[
LatestContraction >
1.35 \times PreviousContraction
\]

or:

```text
Close < SMA50
AND SMA50Slope <= 0
```

The pattern record must remain stored with:

```text
State = INVALIDATED
```

---

# 40. VCP Quality Score

Recommended initial weighting:

| Component | Weight |
|---|---:|
| Contraction progression | 25 |
| ATR compression | 15 |
| Volume compression | 15 |
| Low progression | 10 |
| Pivot quality | 10 |
| Base geometry | 10 |
| Trend context | 10 |
| Relative strength | 5 |
| **Total** | **100** |

---

# 41. VCP Maturity Score

Suggested factors:

| Factor | Weight |
|---|---:|
| Required contraction count present | 25 |
| Final contraction tightness | 20 |
| ATR compression | 15 |
| Volume compression | 10 |
| Pivot clearly defined | 15 |
| Distance to pivot | 15 |
| **Total** | **100** |

---

# 42. PRIMARY PATTERN: BASE-FLAT

A flat base is a controlled, relatively narrow consolidation with repeatedly tested support and resistance.

---

# 43. BASE-FLAT Duration

Default:

```text
20 to 60 trading sessions
```

---

# 44. BASE-FLAT Depth

\[
Depth =
\frac{
HighestHigh_{base} - LowestLow_{base}
}{
HighestHigh_{base}
}
\times100
\]

Default:

```text
Depth <= 15%
```

Preferred:

```text
Depth <= 12%
```

---

# 45. Flat Base Resistance Quality

Require at least:

```text
2 confirmed swing highs
```

within one resistance cluster.

Preferred:

```text
3 or more
```

Resistance dispersion:

\[
ResistanceDispersion =
\frac{
StdDev(ResistanceHighs)
}{
Mean(ResistanceHighs)
}
\times100
\]

Preferred:

```text
< 1.5%
```

---

# 46. Flat Base Support Quality

At least:

```text
2 meaningful support interactions
```

inside one support cluster.

Support dispersion can use the same formula.

---

# 47. Flatness Measurement

Run ordinary least-squares linear regression on closing prices inside the candidate window:

\[
Close_t = a + bt
\]

Calculate total fitted movement:

\[
RegressionMove =
\frac{
|b| \times BaseDuration
}{
MeanClose
}
\times100
\]

Preferred:

```text
RegressionMove < 5%
```

This prevents strong directional trends from being classified as flat bases.

---

# 48. Flat Base ATR Compression

\[
ATRCompression =
\frac{
MedianATR(last\ third)
}{
MedianATR(first\ third)
}
\]

Preferred:

```text
<= 0.85
```

---

# 49. Flat Base Volume Compression

\[
VolumeCompression =
\frac{
MedianVolume(last\ third)
}{
MedianVolume(first\ third)
}
\]

Preferred:

```text
<= 0.85
```

Strong:

```text
<= 0.65
```

---

# 50. Flat Base Pivot

Use:

```text
Median of resistance-zone highs
```

---

# 51. Flat Base READY State

Recommended:

```text
DistanceToPivot <= 3%
AND Depth <= 15%
AND Quality >= 70
```

---

# 52. Flat Base Quality Score

| Component | Weight |
|---|---:|
| Base depth | 20 |
| Resistance quality | 20 |
| Support quality | 15 |
| Flatness | 15 |
| ATR compression | 10 |
| Volume compression | 10 |
| Trend context | 10 |
| **Total** | **100** |

---

# 53. Flat Base Invalidation

Invalidate when:

```text
Close < Support - tolerance
```

or:

```text
Depth expands beyond configured maximum
```

or the flatness/structure substantially breaks.

---

# 54. PRIMARY PATTERN: BASE-52WH

This pattern represents a stock that is consolidating persistently near its 52-week high.

It is not enough for a stock merely to touch a 52-week high once.

---

# 55. 52-Week High

\[
High52W =
HighestHigh(previous\ 252\ sessions)
\]

Distance:

\[
Distance52W =
\frac{
High52W - Close
}{
High52W
}
\times100
\]

Candidate:

```text
Distance52W <= 10%
```

Preferred:

```text
<= 5%
```

---

# 56. BASE-52WH Consolidation Window

Default:

```text
20 to 80 sessions
```

---

# 57. BASE-52WH Base Depth

Preferred:

```text
BaseDepth <= 20%
```

Strong:

```text
<= 12%
```

---

# 58. Persistence Near High

Define:

\[
NearHighThreshold = 12\%
\]

Count:

```text
Number of closes within 12% of High52W
```

Persistence ratio:

\[
Persistence =
\frac{
ClosesWithinThreshold
}{
BaseDuration
}
\]

Default:

```text
Persistence >= 0.60
```

---

# 59. BASE-52WH Quality Score

| Component | Weight |
|---|---:|
| Proximity to 52W high | 25 |
| Persistence near high | 20 |
| Base depth | 15 |
| ATR compression | 10 |
| Volume compression | 10 |
| RS percentile | 10 |
| Trend quality | 10 |
| **Total** | **100** |

---

# 60. BASE-52WH READY

Recommended:

```text
Distance52W <= 5%
AND Quality >= 70
```

Strong ready setup:

```text
Distance52W <= 3%
AND Quality >= 85
```

---

# 61. PRIMARY PATTERN: BRK-RANGE

`BRK-RANGE` is the generic breakout detector.

Other breakout types reuse this engine and change only the source of resistance.

Examples:

```text
BRK-RANGE
BRK-52WH
BRK-ATH
BRK-2Y
BRK-3Y
BRK-5Y
```

---

# 62. Range Resistance

Use confirmed swing-high resistance clusters inside a configurable lookback.

Default:

```text
20 to 120 sessions
```

Require:

```text
at least 2 resistance tests
```

Preferred:

```text
3 or more
```

---

# 63. Breakout Trigger

\[
Close >
Pivot \times (1 + BreakoutBuffer)
\]

---

# 64. Breakout Magnitude in ATR

\[
BreakoutATR =
\frac{
Close - Pivot
}{
ATR14
}
\]

Interpretation:

```text
< 0.25 ATR      Weak
0.25-0.75 ATR   Normal
0.75-1.50 ATR   Strong
1.50-2.00 ATR   Very strong
> 2.00 ATR      Potentially extended
```

---

# 65. Breakout Volume

\[
BreakoutVolumeRatio =
\frac{
Volume_t
}{
MedianVolume_{20}
}
\]

Interpretation:

```text
< 1.0       Weak
1.0-1.3     Acceptable
1.3-2.0     Strong
> 2.0       Very strong
```

Volume should contribute to breakout quality but should not be an absolute requirement.

---

# 66. Breakout Closing Strength

Preferred:

```text
CLV >= 0.70
```

Excellent:

```text
CLV >= 0.85
```

---

# 67. Breakout Range Expansion

\[
RangeExpansion =
\frac{
High_t-Low_t
}{
ATR14
}
\]

Preferred:

```text
>= 1.0
```

Strong:

```text
>= 1.5
```

---

# 68. Extended Breakout Detection

Mark a breakout as `EXTENDED` if:

\[
Close > Pivot + 2 \times ATR14
\]

or:

\[
Close > Pivot \times 1.05
\]

whichever threshold is reached first.

The breakout remains valid but should not be ranked as an optimal fresh entry.

---

# 69. Breakout Quality Score

| Component | Weight |
|---|---:|
| Resistance quality | 20 |
| Breakout magnitude | 15 |
| Volume expansion | 20 |
| Closing strength | 15 |
| Range/ATR expansion | 10 |
| Source base quality | 10 |
| Trend/RS context | 10 |
| **Total** | **100** |

---

# 70. Breakout Lifecycle

### TRIGGERED

On first valid breakout close.

### CONFIRMED

Example rule:

```text
2 closes above pivot
```

or:

```text
Strong breakout close
AND next session does not fail
```

### FAILED

If the breakout returns below the pivot within the configured failure window.

---

# 71. FAILED BREAKOUT Logic

Default observation window:

```text
5 sessions after trigger
```

Failure:

\[
Close <
Pivot \times (1 - BreakoutBuffer)
\]

Strong failure:

```text
Close < breakout candle low
AND VolumeRatio20 >= 1.3
```

Emit:

```text
FAIL-BRK
```

---

# 72. BRK-52WH

Use the generic breakout engine where:

```text
Pivot = prior 252-session high
```

Preferably the previous high excludes the current breakout session.

---

# 73. BRK-ATH

Use:

```text
Pivot = highest historical adjusted high before current session
```

The historical data set must be complete enough to make this classification meaningful.

---

# 74. BRK-MULTIY

Variants:

```text
BRK-2Y
BRK-3Y
BRK-5Y
```

Approximate lookbacks:

```text
2Y = 504 sessions
3Y = 756 sessions
5Y = 1260 sessions
```

Add measurements:

```text
ResistanceAge
HistoricalTestCount
```

---

# 75. PRIMARY PATTERN: PB-BRKRET

Breakout retest identifies price returning to a recently broken resistance level that may now behave as support.

It requires a previously detected breakout.

---

# 76. PB-BRKRET Source Pattern

Source breakout may be:

```text
BRK-RANGE
BRK-BASE
BRK-52WH
BRK-ATH
BRK-MULTIY
```

Store:

```text
SourcePatternInstanceId
OriginalPivot
OriginalBreakoutDate
OriginalBreakoutQuality
```

---

# 77. Minimum Advance Before Retest

The breakout should first prove successful.

Require:

\[
MaximumAdvance \ge \max(3\%, 1 \times ATR14)
\]

Percentage maximum advance:

\[
MaximumAdvancePct =
\frac{
HighestHighAfterBreakout - Pivot
}{
Pivot
}
\times100
\]

---

# 78. Retest Timing

Default valid retest window:

```text
3 to 30 sessions after breakout
```

Preferred:

```text
5 to 20 sessions
```

---

# 79. Retest Zone

Define:

\[
RetestTolerance =
Clamp(
0.5 \times NATR14,
1.0\%,
2.5\%
)
\]

Valid zone:

\[
Pivot(1-RetestTolerance)
\le Low
\le
Pivot(1+RetestTolerance)
\]

Example:

```text
Pivot = 500
Tolerance = 1.5%

Retest zone:
492.50 to 507.50
```

---

# 80. Retest Volume

\[
RetestVolumeRatio =
\frac{
MedianVolume(PullbackPeriod)
}{
MedianVolume_{20}
}
\]

Preferred:

```text
< 0.85
```

Strong:

```text
< 0.65
```

---

# 81. Retest State

### FORMING

Price begins to pull back after a confirmed breakout.

### READY

Price enters the retest zone.

### TRIGGERED

Conservative rule:

```text
Close > RetestSwingHigh + BreakoutBuffer
```

Alternative faster rule:

```text
Close > previous day's high
```

V1 should favor the conservative rule.

---

# 82. Retest Invalidation

Invalidate if:

```text
2 consecutive closes below:
Pivot * (1 - RetestTolerance)
```

or:

```text
single close below Pivot - 1 * ATR14
```

---

# 83. PB-BRKRET Quality Score

| Component | Weight |
|---|---:|
| Original breakout quality | 20 |
| Retest proximity | 20 |
| Pullback volume | 20 |
| Retest depth | 15 |
| Bounce/closing behavior | 10 |
| RS retention | 10 |
| Retest timing | 5 |
| **Total** | **100** |

---

# 84. PRIMARY PATTERN: PB-EMA20

EMA20 pullback is a continuation setup inside a strong trend.

---

# 85. EMA20 Trend Prerequisites

Recommended:

```text
EMA20 > SMA50
SMA50 > SMA200

EMA20Slope > 0
SMA50Slope > 0
```

Additionally:

```text
At least 10 of previous 15 closes > EMA20
```

before the pullback begins.

---

# 86. EMA20 Pullback Depth

From recent confirmed swing high:

\[
PullbackDepth =
\frac{
SwingHigh - CurrentLow
}{
SwingHigh
}
\times100
\]

Preferred:

```text
3% to 12%
```

---

# 87. EMA20 Pullback Duration

Preferred:

```text
2 to 10 sessions
```

---

# 88. EMA20 Touch Zone

\[
TouchTolerance =
Clamp(
0.5 \times NATR14,
0.75\%,
2.00\%
)
\]

A valid touch occurs if the session low comes within the tolerance band surrounding EMA20.

---

# 89. EMA20 Pullback Volume

\[
PullbackVolumeRatio =
\frac{
MedianVolume(PullbackPeriod)
}{
MedianVolume_{20}
}
\]

Preferred:

```text
< 0.85
```

Strong:

```text
< 0.70
```

---

# 90. EMA20 Price Behavior

Preferred:

```text
Close >= EMA20
CLV >= 0.60
```

A bullish reversal candle may improve quality but should not be mandatory.

---

# 91. EMA20 Trigger

Recommended V1 trigger:

```text
Close > HighestHigh(previous 2 sessions)
```

after a valid EMA20 touch.

Faster alternative:

```text
Close > EMA20
AND CLV >= 0.65
```

---

# 92. EMA20 Invalidation

Invalidate if:

```text
2 consecutive closes below EMA20
```

with significant penetration, for example:

```text
Close < EMA20 - 1 * ATR14
```

or:

```text
Close < recent structural swing low
```

If price continues lower toward SMA50, the EMA20 pattern may be invalid while a separate `PB-SMA50` candidate begins.

---

# 93. EMA20 Quality Score

| Component | Weight |
|---|---:|
| Trend quality | 25 |
| EMA20 proximity | 15 |
| Pullback depth | 15 |
| Pullback volume | 15 |
| Pullback duration | 10 |
| Closing behavior | 10 |
| RS retention | 10 |
| **Total** | **100** |

---

# 94. PRIMARY PATTERN: PB-SMA50

The SMA50 pullback is structurally deeper and generally slower than EMA20 pullback.

---

# 95. SMA50 Trend Requirements

```text
SMA50 > SMA200
SMA50Slope > 0
```

Before pullback:

```text
Price > SMA50
for at least 70% of previous 40 sessions
```

---

# 96. SMA50 Pullback Depth

From recent confirmed swing high:

```text
5% to 20%
```

---

# 97. SMA50 Pullback Duration

Recommended:

```text
3 to 20 sessions
```

---

# 98. SMA50 Touch Zone

\[
TouchTolerance =
Clamp(
0.5 \times NATR14,
1.0\%,
2.5\%
)
\]

Allow limited penetration if price recovers.

---

# 99. SMA50 Touch Count

Count distinct prior SMA50 pullback episodes during the previous 126 sessions.

Touch episodes must be separated by at least:

```text
10 sessions
```

Variants:

```text
PB-SMA50-T1
PB-SMA50-T2
PB-SMA50-T3+
```

---

# 100. SMA50 Pullback Volume

Use:

\[
PullbackVolumeRatio =
\frac{
MedianVolume(PullbackPeriod)
}{
MedianVolume_{20}
}
\]

Preferred:

```text
< 0.85
```

---

# 101. SMA50 Bounce Confirmation

Preferred:

```text
Close > SMA50
AND CLV >= 0.60
```

Trigger:

```text
Close > HighestHigh(previous 2 sessions)
```

after the SMA50 test.

---

# 102. SMA50 Invalidation

Invalidate if:

```text
2 closes below SMA50 by more than 1 ATR
```

or:

```text
SMA50Slope <= 0
AND structural swing low fails
```

---

# 103. SMA50 Quality Score

| Component | Weight |
|---|---:|
| Trend quality | 25 |
| SMA50 slope | 15 |
| Touch quality | 15 |
| Pullback volume | 15 |
| Pullback depth | 10 |
| Bounce strength | 10 |
| RS retention | 10 |
| **Total** | **100** |

---

# 104. SUPPORTING PATTERN: BASE-TIGHT

Represents narrow consolidation.

Measurements:

```text
Range5
Range10
Range20
ATR5 / ATR20
CloseDispersion
Volume5 / Volume20
InsideBarCount
```

Suggested strong conditions:

```text
Range10 <= 5%
ATR5 / ATR20 <= 0.65
Volume5 / Volume20 <= 0.70
```

This pattern can frequently coexist with `BASE-VCP` or `BASE-52WH`.

---

# 105. SUPPORTING PATTERN: TREND-HHHL

Use confirmed swing pivots.

Uptrend evidence:

```text
Latest swing high > prior swing high
Latest swing low  > prior swing low
```

Measurements:

```text
HigherHighRatio
HigherLowRatio
TrendDuration
AveragePullbackDepth
AverageSwingDuration
NormalizedTrendSlope
```

Ratios:

\[
HigherHighRatio =
\frac{
Count(HH)
}{
Count(HighComparisons)
}
\]

\[
HigherLowRatio =
\frac{
Count(HL)
}{
Count(LowComparisons)
}
\]

---

# 106. SUPPORTING PATTERN: TREND-S2

Stage-2 style trend.

Preferred conditions:

```text
Close > 30-week MA
30-week MA rising
Close > SMA50
SMA50 > SMA200
SMA50Slope > 0
SMA200Slope >= 0
```

Measurements:

```text
StageDuration
30WeekSlope
DistanceAbove30WeekMA
52WRangePosition
RSPercentile
```

---

# 107. SUPPORTING PATTERN: TREND-MA

Moving-average alignment.

Example score components:

```text
Close > EMA20
EMA20 > SMA50
SMA50 > SMA100
SMA100 > SMA200
EMA20Slope > 0
SMA50Slope > 0
SMA200Slope >= 0
```

Normalize to:

```text
MAAlignmentScore = 0-100
```

---

# 108. SUPPORTING PATTERN: COMP-NR7

Daily range:

\[
DailyRangePct =
\frac{
High-Low
}{
Close
}
\times100
\]

`NR7` occurs when today's range is the smallest of the previous seven sessions.

Measurements:

```text
DailyRangePct
RankWithin7
NATR14
VolumeRatio20
```

---

# 109. SUPPORTING PATTERN: COMP-IB

An inside bar occurs when:

```text
High[t] <= High[t-1]
AND
Low[t] >= Low[t-1]
```

Variants:

```text
COMP-IB1
COMP-IB2
COMP-IB3
```

Measurements:

```text
MotherBarRange
InsideBarCount
CompressionRatio
VolumeContraction
```

Compression:

\[
CompressionRatio =
\frac{
CurrentInsideRange
}{
MotherBarRange
}
\]

---

# 110. SUPPORTING PATTERN: COMP-ATR

Measurements:

```text
ATR5
ATR10
ATR20
ATR50

ATR5 / ATR20
ATR10 / ATR50
ATRPercentile1Y
```

Strong compression examples:

```text
ATR5 / ATR20 <= 0.65
ATRPercentile1Y <= 20
```

---

# 111. SUPPORTING PATTERN: COMP-RANGE

Measurements:

```text
Range5
Range10
Range20
Range50
```

Ratios:

\[
RangeCompression5_20 =
\frac{Range5}{Range20}
\]

\[
RangeCompression10_50 =
\frac{Range10}{Range50}
\]

---

# 112. SUPPORTING PATTERN: MOM-ACC

Measure absolute momentum across multiple horizons.

Recommended:

```text
Return1M  = 21 sessions
Return3M  = 63 sessions
Return6M  = 126 sessions
Return12M = 252 sessions
```

A simple acceleration framework can compare short-term momentum to longer-term average pace.

Example normalized pace:

\[
MonthlyPace_1M = Return1M
\]

\[
MonthlyPace_3M = \frac{Return3M}{3}
\]

\[
MonthlyPace_6M = \frac{Return6M}{6}
\]

Momentum acceleration is stronger when:

```text
MonthlyPace1M > MonthlyPace3M > MonthlyPace6M
```

This should be scored continuously rather than as a binary rule.

---

# 113. SUPPORTING PATTERN: MOM-RSL

Relative Strength Leader.

Calculate benchmark excess return for:

```text
1M
3M
6M
12M
```

Convert each to cross-sectional percentile.

A simple composite:

\[
RSComposite =
0.10 RS1M +
0.25 RS3M +
0.35 RS6M +
0.30 RS12M
\]

Initial interpretation:

```text
>= 90    Elite RS
80-90    Strong
60-80    Above average
40-60    Neutral
< 40     Weak
```

Weights should later be validated through backtesting.

---

# 114. SUPPORTING PATTERN: MOM-RSB

Relative-strength breakout.

Construct relative-price series:

\[
R_t =
\frac{
StockClose_t
}{
BenchmarkClose_t
}
\]

Detect new rolling highs in this ratio.

Variants may include:

```text
RS-20D-HIGH
RS-50D-HIGH
RS-252D-HIGH
```

Measurements:

```text
RS20Breakout
RS50Breakout
RS252Breakout
RSSlope
```

---

# 115. SUPPORTING SIGNAL: VOL-DRY

Volume dry-up should be treated as a supporting signal.

Example metric:

\[
VolumeDryUpRatio =
\frac{
MedianVolume_5
}{
MedianVolume_{50}
}
\]

Interpretation:

```text
> 0.90     None
0.70-0.90  Mild
0.50-0.70  Strong
< 0.50     Very strong
```

---

# 116. SUPPORTING SIGNAL: VOL-EXP

\[
VolumeExpansion =
\frac{
Volume_t
}{
MedianVolume_{20}
}
\]

Interpretation:

```text
1.0-1.3    Mild
1.3-2.0    Strong
>2.0       Very strong
```

---

# 117. Optional Delivery Measurements

If NSE delivery data is available, calculate:

```text
DeliveryPct
MedianDeliveryPct5
MedianDeliveryPct20
DeliveryExpansion
DeliverableVolume
```

\[
DeliveryExpansion =
\frac{
MedianDeliveryPct_5
}{
MedianDeliveryPct_{20}
}
\]

Delivery information should be treated as supporting evidence.

Do not label it as institutional buying.

---

# 118. FAILURE PATTERN: FAIL-BRK

Already described under breakout logic.

Measurements:

```text
OriginalPivot
HighestAdvanceAfterBreakout
DaysAbovePivot
DistanceBelowPivot
FailureVolumeRatio
CloseBelowBreakoutCandle
RSDeterioration
```

---

# 119. FAILURE PATTERN: FAIL-BASE

A previously detected base breaks structurally below support.

Trigger example:

```text
Close < Support - SupportTolerance
```

Measurements:

```text
SupportLevel
SupportPenetrationPct
VolumeRatio20
TrendScore
DistanceBelowSMA50
```

---

# 120. FAILURE PATTERN: FAIL-EMA20

Avoid flagging on one insignificant close.

Suggested conditions:

```text
At least 2 closes below EMA20
```

and one of:

```text
Penetration > 1 ATR
OR
Recent swing low broken
```

Measurements:

```text
DaysBelowEMA20
MaximumPenetrationATR
VolumeDuringFailure
PreviousTrendQuality
```

---

# 121. FAILURE PATTERN: FAIL-SMA50

Suggested detection:

```text
2 closes below SMA50
AND penetration >= 1 ATR
```

Stronger failure if:

```text
SMA50Slope <= 0
```

Measurements:

```text
BreakPct
BreakATR
VolumeExpansion
SMA50Slope
DaysBelow
FailedReclaimCount
```

---

# 122. FAILURE PATTERN: FAIL-STRUCT

Uptrend structure fails when a meaningful swing low is broken.

For an HH/HL structure:

```text
Latest close < previous confirmed major swing low
```

Measurements:

```text
BrokenSwingLow
BreakPct
BreakATR
VolumeRatio20
RSDeterioration
TrendAge
```

---

# 123. Pattern Quality vs Maturity vs Context

These are separate concepts.

## Pattern Quality

> How clean is the detected geometry?

Example:

```text
VCP Quality = 94
```

---

## Pattern Maturity

> How close is the pattern to the point where it can transition to a trigger?

Example:

```text
VCP Maturity = 72
```

---

## Context Score

> How favorable is the surrounding technical environment?

Example:

```text
Market     78
Sector     91
Trend      92
RS         95
Liquidity  90

Context = 90
```

---

# 124. Pattern Maturity Bands

Use common display bands:

```text
0-39     EARLY
40-64    FORMING
65-79    MATURE
80-89    READY
90-100   IMMINENT
```

The numerical calculation of maturity is pattern-specific.

---

# 125. Generic Pattern Lifecycle

Recommended states:

```text
DETECTED
FORMING
MATURE
READY
TRIGGERED
CONFIRMED
FAILED
INVALIDATED
EXPIRED
```

Not every pattern uses every state.

---

# 126. VCP Lifecycle Example

```text
DETECTED
   |
FORMING
   |
MATURE
   |
READY
   |
TRIGGERED
   |
CONFIRMED
```

Failure branch:

```text
TRIGGERED
   |
FAILED
```

Structural break before trigger:

```text
FORMING / MATURE / READY
   |
INVALIDATED
```

---

# 127. Setup Score

The setup score ranks detected opportunities.

Pattern detection and setup ranking remain separate.

Recommended initial formula:

\[
SetupScore =
0.35 PatternQuality +
0.20 PatternMaturity +
0.15 TrendScore +
0.15 RelativeStrengthScore +
0.10 SectorScore +
0.05 VolumeScore
\]

All components must be normalized to 0-100.

This formula is only a V1 default.

Backtesting should later determine optimal weights.

---

# 128. Context Engine Measurements

Recommended context fields:

```text
MarketRegimeScore
SectorStrengthScore
TrendScore
RelativeStrengthScore
VolumeScore
LiquidityScore
```

---

# 129. Liquidity Filter

The pattern engine may detect patterns in all equities, but user-facing opportunity ranking should filter illiquid securities.

Potential EOD filters:

```text
MinimumClosePrice
MedianTradedValue20
MedianVolume20
MinimumTradingHistory
```

Example configurable defaults:

```text
Price >= Rs.20
History >= 250 sessions
Median traded value 20D >= Rs.2 crore
```

The exact commercial universe should be decided separately.

---

# 130. Market Regime Inputs

The pattern engine itself should not depend on market regime, but setup ranking may.

Useful market measurements:

```text
NIFTY500 > EMA20
NIFTY500 > SMA50
NIFTY500 > SMA200

EMA20 slope
SMA50 slope

Percentage of stocks above EMA20
Percentage above SMA50
Percentage above SMA200

New 52W highs
New 52W lows
Breakouts
Failed breakouts
```

---

# 131. Sector Strength Inputs

For each sector/index:

```text
1M relative strength
3M relative strength
6M relative strength
12M relative strength

Percentage of constituents above SMA50
Percentage above SMA200
Number of Stage-2 stocks
Number of breakouts
Number of failures
```

---

# 132. Technical Fingerprint

Every stock should ultimately resolve to a standardized technical fingerprint.

Example:

```text
TECHNICAL FINGERPRINT
--------------------------------

Trend
Stage 2                    91
HH/HL                      Active

Primary Setup
VCP-3C                     92

State
READY

Maturity
88

Compression
COMP-ATR                   89
COMP-NR7                   Active

Momentum
MOM-ACC                    86

Relative Strength
RS1M                       82
RS3M                       91
RS6M                       96
RS12M                      94

Volume
Vol5 / Vol50               0.52
State                      Contracting

Location
52W High                   -2.8%
Pivot                      -1.7%
EMA20                      +2.1%
SMA50                      +6.4%

Context
Market                     78
Sector                     91

Pattern Quality            92
Setup Score                89
```

---

# 133. Standard Pattern Instance Schema

Recommended conceptual schema:

```json
{
  "securityId": "uuid",
  "patternInstanceId": "uuid",

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

  "measurements": {
    "baseDuration": 38,
    "baseDepthPct": 16.2,
    "contractionCount": 3,
    "contractionsPct": [14.8, 8.3, 4.7],
    "atrCompression": 0.58,
    "volumeCompression": 0.51,
    "pivotDistancePct": 1.7,
    "rs6mPercentile": 94
  },

  "supportingPatterns": [
    "TREND-S2",
    "TREND-HHHL",
    "COMP-ATR",
    "MOM-RSL",
    "VOL-DRY"
  ]
}
```

---

# 134. Pattern Event History

Do not overwrite the current state without preserving historical transitions.

Store events such as:

```text
PATTERN_DETECTED
STATE_CHANGED
PIVOT_UPDATED
QUALITY_CHANGED
MATURITY_CHANGED
TRIGGERED
CONFIRMED
FAILED
INVALIDATED
EXPIRED
```

Example timeline:

```text
Aug 19  VCP detected
Aug 24  Second contraction confirmed
Aug 29  Volume dry-up detected
Sep 01  Third contraction confirmed
Sep 02  Maturity crossed 80
Sep 02  FORMING -> READY
Sep 04  Breakout triggered
```

This enables the user-facing Technical Timeline.

---

# 135. Pattern Deduplication

A detector running every day must not create a new pattern instance every day.

A new detection should update an existing active pattern if:

```text
Same security
Same pattern type
Overlapping pattern window
Same or similar pivot/base
Existing state not terminal
```

Terminal states:

```text
FAILED
INVALIDATED
EXPIRED
```

---

# 136. Pattern Expiry

Patterns should not live indefinitely.

Examples:

### VCP / Flat Base

Expire if:

```text
Maximum configured base duration exceeded
AND no meaningful updated structure exists
```

### Breakout Retest

Expire after:

```text
30 sessions after breakout
```

if no valid retest occurred.

### EMA20 Pullback

Expire if:

```text
pullback lasts > configured maximum
```

or transitions to another structural pattern.

---

# 137. Backtesting Requirements

Backtesting is not optional because every threshold in this specification is initially heuristic.

The engine must be designed so that historical tests can answer:

```text
How did BASE-VCP perform?
```

and more importantly:

```text
How did BASE-VCP perform when:
RS6M > 90
AND TREND-S2 active
AND SectorScore > 80
AND VolumeCompression < 0.60?
```

---

# 138. Avoid Look-Ahead Bias

Critical rules:

1. Swing highs/lows may only become available on their confirmation date.
2. 52-week highs should exclude the current breakout bar when testing breakout trigger.
3. Corporate-action adjustments must be point-in-time correct where possible.
4. Index constituents used in historical breadth should ideally be point-in-time constituent sets.
5. Do not calculate a pattern using future candles.

---

# 139. Backtest Outcome Measurements

For every triggered setup record:

```text
EntryDate
EntryPrice
PatternType
PatternQuality
Maturity
Context
SetupScore
```

Then calculate:

```text
Return5D
Return10D
Return20D
Return40D
Return60D

MaximumFavorableExcursion
MaximumAdverseExcursion

DaysTo5Percent
DaysTo10Percent
DaysTo20Percent

Hit5BeforeMinus5
Hit10BeforeMinus8
Hit20BeforeMinus8
```

---

# 140. Maximum Favorable Excursion

For holding window \(N\):

\[
MFE_N =
\frac{
HighestHigh_{nextN} - Entry
}{
Entry
}
\times100
\]

---

# 141. Maximum Adverse Excursion

\[
MAE_N =
\frac{
LowestLow_{nextN} - Entry
}{
Entry
}
\times100
\]

Typically this will be negative.

---

# 142. Pattern Research Example

The platform should later support analysis such as:

```text
BASE-VCP
2018-2026

Occurrences              4,823
Median 20D return         +5.1%
Median 60D return         +10.8%
Median MFE60              +14.4%
Median MAE60              -5.6%
```

Then filter:

```text
BASE-VCP
RS6M > 90
TREND-S2
MarketRegime > 70
```

and compare the result.

This is one of the long-term differentiators of the platform.

---

# 143. Recommended Detector Execution Order

Run feature computation first.

```text
1. Data normalization
2. Corporate-action adjustment
3. Technical feature computation
4. Swing detection
5. Support/resistance clustering
6. Supporting trend/compression/momentum signals
7. Primary base detectors
8. Breakout detectors
9. Pullback detectors
10. Failure detectors
11. Quality/maturity scoring
12. Context engine
13. Setup scoring
14. Pattern lifecycle update
15. Persistence and event generation
```

---

# 144. Detector Interface

Conceptual interface:

```text
IPatternDetector

Detect(
    Security security,
    IReadOnlyList<DailyBar> bars,
    TechnicalFeatureSeries features,
    DetectionContext context
) -> IReadOnlyList<PatternCandidate>
```

A detector should not directly save to the database.

The lifecycle service decides whether a candidate creates, updates, or terminates a pattern instance.

---

# 145. Supporting Engine Interfaces

Recommended components:

```text
IFeatureEngine
ISwingDetector
ISupportResistanceEngine
IPatternDetector
IPatternQualityScorer
IPatternMaturityScorer
IContextEngine
ISetupScorer
IPatternLifecycleService
IPatternRepository
IBacktestEngine
```

---

# 146. Configuration Structure

Example:

```yaml
vcp:
  minDuration: 20
  maxDuration: 90
  minDepthPct: 8
  maxDepthPct: 35
  minContractions: 2
  maxContractions: 5
  readyPivotDistancePct: 3
  readyMaturity: 80
  maxFinalContractionPct: 8

flatBase:
  minDuration: 20
  maxDuration: 60
  maxDepthPct: 15
  readyPivotDistancePct: 3

breakout:
  minResistanceTests: 2
  lookbackMin: 20
  lookbackMax: 120
  failureWindowSessions: 5

breakoutRetest:
  minSessionsAfterBreakout: 3
  maxSessionsAfterBreakout: 30
  preferredMinSessions: 5
  preferredMaxSessions: 20

ema20Pullback:
  minDepthPct: 3
  maxDepthPct: 12
  minDuration: 2
  maxDuration: 10

sma50Pullback:
  minDepthPct: 5
  maxDepthPct: 20
  minDuration: 3
  maxDuration: 20
```

---

# 147. Initial V1 Scope

The first production-quality implementation should prioritize these seven core detectors:

```text
1. BASE-VCP
2. BASE-FLAT
3. BASE-52WH
4. BRK-RANGE
5. PB-BRKRET
6. PB-EMA20
7. PB-SMA50
```

And supporting detectors:

```text
TREND-HHHL
TREND-S2
TREND-MA

COMP-NR7
COMP-IB
COMP-ATR
COMP-RANGE

MOM-ACC
MOM-RSL
MOM-RSB

VOL-DRY
VOL-EXP
```

Failure detectors:

```text
FAIL-BRK
FAIL-BASE
FAIL-EMA20
FAIL-SMA50
FAIL-STRUCT
```

---

# 148. Why This Structure Is Important

The technical advantage of the product should not be:

> We detect more chart pattern names than other websites.

The differentiator should be:

> **Every pattern is measured, scored, contextualized, tracked through time, and historically testable.**

A detected VCP is not simply:

```text
VCP = true
```

It is:

```text
Pattern              VCP-3C
State                READY

Base Duration        38 sessions
Base Depth           16.2%

C1                   14.8%
C2                    8.3%
C3                    4.7%

ATR Compression      0.58
Volume Compression   0.51

Pivot                500
DistanceToPivot      1.7%

Pattern Quality      92
Maturity             88
Context              90
Setup Score          89

Supporting
TREND-S2
MOM-RSL
COMP-ATR
VOL-DRY

Invalidation         457
```

This is the technical fingerprint that should drive the product.

---

# 149. Final Canonical Model

The platform architecture around patterns should be:

```text
                    EOD MARKET DATA
                          |
                          v
                   NORMALIZATION
                          |
                          v
                    FEATURE ENGINE
                          |
        +-----------------+----------------+
        |                 |                |
        v                 v                v
      TREND            VOLATILITY        VOLUME
        |                 |                |
        +-----------------+----------------+
                          |
                          v
                    SWING ENGINE
                          |
                          v
              SUPPORT / RESISTANCE
                          |
                          v
                  PATTERN DETECTORS
                          |
        +-----------------+-------------------+
        |                                     |
        v                                     v
   PRIMARY SETUPS                       SUPPORTING SIGNALS
        |                                     |
        +------------------+------------------+
                           |
                           v
                    QUALITY SCORE
                           |
                           v
                    MATURITY SCORE
                           |
                           v
                     CONTEXT ENGINE
                           |
                           v
                      SETUP SCORE
                           |
                           v
                    LIFECYCLE ENGINE
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
      USER EXPERIENCE                   BACKTEST
```

---

# 150. Final Product Interpretation

The website should never imply:

```text
Setup Score 92 = 92% chance of profit
```

Instead:

```text
Setup Score 92
```

means:

> The current setup ranks very highly according to the configured technical quality, maturity, trend, relative strength, sector, and volume framework.

Historical probability must be reported separately and only after sufficient backtesting.

---

# 151. Recommended Next Engineering Step

Implementation should begin with the shared foundations rather than with individual patterns.

Recommended order:

```text
Phase 1
------
DailyBar model
Adjusted OHLCV
ATR
EMA/SMA
Rolling range
Volume normalization
Relative strength

Phase 2
------
Swing engine
Support/resistance clustering
Pivot confirmation rules

Phase 3
------
TREND-HHHL
TREND-S2
COMP-ATR
VOL-DRY
MOM-RSL

Phase 4
------
BASE-FLAT
BASE-52WH
BASE-VCP

Phase 5
------
BRK-RANGE
BRK-52WH
BRK-ATH
BRK-MULTIY

Phase 6
------
PB-BRKRET
PB-EMA20
PB-SMA50

Phase 7
------
FAIL-BRK
FAIL-BASE
FAIL-EMA20
FAIL-SMA50
FAIL-STRUCT

Phase 8
------
Quality scoring
Maturity scoring
Context scoring
Setup scoring
Lifecycle persistence

Phase 9
------
Historical backtesting
Threshold calibration
Pattern research UI
```

---

# 152. Summary

The finalized technical-pattern system consists of:

### Primary setup families

```text
BASE-VCP
BASE-FLAT
BASE-52WH
BRK-RANGE / BRK-52WH / BRK-ATH / BRK-MULTIY
PB-BRKRET
PB-EMA20
PB-SMA50
```

### Supporting technical state

```text
TREND-HHHL
TREND-S2
TREND-MA
BASE-TIGHT
COMP-NR7
COMP-IB
COMP-ATR
COMP-RANGE
MOM-ACC
MOM-RSL
MOM-RSB
VOL-DRY
VOL-EXP
```

### Failure state

```text
FAIL-BRK
FAIL-BASE
FAIL-EMA20
FAIL-SMA50
FAIL-STRUCT
```

Every pattern instance is defined by:

```text
Classification
Identifier
Geometry
Measurements
Quality
Maturity
State
Trigger
Pivot
Support
Invalidation
Context
Lifecycle
Historical outcome
```

This document should be treated as the initial canonical contract for the pattern-analysis engine. Numeric thresholds should be implemented as configurable defaults and validated through historical backtesting before the platform makes any claims about the effectiveness of a setup.
