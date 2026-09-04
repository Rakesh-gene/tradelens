"""Shared, deterministic technical-feature calculations over adjusted EOD bars."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from statistics import median
from typing import Mapping, Sequence

from pattern_engine.models import serialize_value
from repositories.market_data import MarketDataRepository


LOOKBACK = 1260
_D = Decimal


class FeatureService:
    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def rebuild(self, isin: str, from_date: date, to_date: date, adjustment_version: str, feature_version: str, *, changed_from_date: date | None = None, benchmark_bars: Sequence[Mapping[str, object]] = ()) -> int:
        bars = self._repository.load_adjusted_bars(isin, from_date, to_date, adjustment_version)
        features = compute_features(bars, feature_version, adjustment_version, benchmark_bars)
        if changed_from_date is not None:
            dates = [item["trading_date"] for item in features]
            position = next((index for index, value in enumerate(dates) if value >= changed_from_date), len(dates))
            features = features[max(0, position - LOOKBACK):]
        return self._repository.upsert_technical_features(features)


def compute_features(bars: Sequence[Mapping[str, object]], feature_version: str, data_version: str, benchmark_bars: Sequence[Mapping[str, object]] = ()) -> list[dict[str, object]]:
    """Return one typed feature record per adjusted bar, ordered by trading date."""
    ordered = sorted(bars, key=lambda item: item["trading_date"])
    benchmark = {item["trading_date"]: _decimal(item["close_price"]) for item in benchmark_bars}
    closes = [_decimal(item["close_price"]) for item in ordered]
    highs = [_decimal(item["high_price"]) for item in ordered]
    lows = [_decimal(item["low_price"]) for item in ordered]
    volumes = [_decimal(item["volume"]) for item in ordered]
    traded_values = [closes[index] * volumes[index] for index in range(len(ordered))]
    trs = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) if i else highs[i] - lows[i] for i in range(len(ordered))]
    atrs = {period: _wilder(trs, period) for period in (5, 10, 14, 20, 50)}
    emas = {period: _ema(closes, period) for period in (10, 20)}
    smas = {
        period: [_mean(closes[index - period + 1:index + 1]) if index + 1 >= period else None for index in range(len(closes))]
        for period in (50, 100, 200)
    }
    result = []
    for i, bar in enumerate(ordered):
        row = _blank_feature(bar, feature_version, data_version)
        row["true_range"] = trs[i]
        for period, values in atrs.items(): row[f"atr_{period}"] = values[i]
        row["natr_14"] = _pct(atrs[14][i], closes[i]) if atrs[14][i] is not None else None
        for period, values in emas.items(): row[f"ema_{period}"] = values[i]
        for period, values in smas.items(): row[f"sma_{period}"] = values[i]
        row["ema_20_slope"] = _slope(emas[20], i, 20)
        row["sma_50_slope"] = _slope(smas[50], i, 20)
        row["sma_200_slope"] = _slope(smas[200], i, 20)
        for period in (5, 10, 20, 50):
            row[f"range_{period}"] = _range_pct(highs[i - period + 1:i + 1], lows[i - period + 1:i + 1]) if i + 1 >= period else None
            row[f"median_volume_{period}"] = _median(volumes[i - period + 1:i + 1]) if i + 1 >= period else None
        row["volume_ratio_20"] = _ratio(volumes[i], row["median_volume_20"])
        row["volume_ratio_5_to_50"] = _ratio(row["median_volume_5"], row["median_volume_50"])
        row["volume_contraction_ratio"] = row["volume_ratio_5_to_50"]
        row["close_location_value"] = _clv(highs[i], lows[i], closes[i])
        row["distance_to_ema_20_pct"] = _distance(closes[i], row["ema_20"])
        row["distance_to_sma_50_pct"] = _distance(closes[i], row["sma_50"])
        row["distance_to_sma_200_pct"] = _distance(closes[i], row["sma_200"])
        row["median_traded_value_20"] = _median(traded_values[i - 19:i + 1]) if i + 1 >= 20 else None
        if i >= 252:
            prior_high, prior_low = max(highs[i - 252:i]), min(lows[i - 252:i])
            row["high_52_week"], row["low_52_week"] = prior_high, prior_low
            row["range_position_52_week"] = _pct(closes[i] - prior_low, prior_high - prior_low)
            row["distance_to_52_week_high_pct"] = _pct(closes[i] - prior_high, prior_high)
        if i:
            ath = max(highs[:i]); row["all_time_high"] = ath; row["distance_to_all_time_high_pct"] = _pct(closes[i] - ath, ath)
        for sessions, name, rs_name in ((21, "1_month", "1m"), (63, "3_month", "3m"), (126, "6_month", "6m"), (252, "12_month", "12m")):
            if i >= sessions:
                row[f"return_{name}"] = _pct(closes[i] - closes[i - sessions], closes[i - sessions])
                benchmark_return = _aligned_return(benchmark, ordered, i, sessions)
                row[f"relative_strength_{rs_name}"] = row[f"return_{name}"] - benchmark_return if benchmark_return is not None else None
        rs = [row[f"relative_strength_{name}"] for name in ("1m", "3m", "6m", "12m") if row.get(f"relative_strength_{name}") is not None]
        row["relative_strength_composite"] = _mean(rs) if rs else None
        delivery = bar.get("delivery_percentage")
        row["delivery_percentage"] = _decimal(delivery) if delivery is not None else None
        deliverable = bar.get("deliverable_quantity")
        row["deliverable_volume"] = _decimal(deliverable) if deliverable is not None else None
        delivery_values_5 = [_decimal(item.get("delivery_percentage")) for item in ordered[max(0, i - 4):i + 1] if item.get("delivery_percentage") is not None]
        delivery_values = [_decimal(item.get("delivery_percentage")) for item in ordered[max(0, i - 19):i + 1] if item.get("delivery_percentage") is not None]
        row["median_delivery_percentage_5"] = _median(delivery_values_5) if len(delivery_values_5) >= 5 else None
        row["median_delivery_percentage_20"] = _median(delivery_values) if len(delivery_values) >= 20 else None
        row["delivery_expansion_ratio"] = _ratio(row["median_delivery_percentage_5"], row["median_delivery_percentage_20"])
        row["input_checksum"] = _checksum(bar, row["trading_date"], data_version)
        result.append(row)
    return result


def _blank_feature(bar, version, data_version):
    return {"isin": bar["isin"], "trading_date": bar["trading_date"], "feature_version": version, "data_version": data_version, "secondary_metrics": {}}
def _decimal(value): return value if isinstance(value, Decimal) else Decimal(str(value))
def _mean(values): return sum(values, Decimal("0")) / len(values) if values else None
def _median(values): return Decimal(str(median(values))) if values else None
def _ratio(a, b): return a / b if a is not None and b not in (None, 0) else None
def _pct(value, denominator): return (value / denominator) * 100 if denominator not in (None, 0) else None
def _range_pct(highs, lows): return _pct(max(highs) - min(lows), max(highs)) if max(highs) else None
def _distance(price, level): return _pct(price - level, level) if level not in (None, 0) else None
def _clv(high, low, close): return Decimal("0.5") if high == low else (close - low) / (high - low)
def _wilder(values, period):
    out=[]; current=None
    for i, value in enumerate(values):
        if i == period - 1: current=_mean(values[:period])
        elif i >= period and current is not None: current=(current * (period - 1) + value) / period
        out.append(current)
    return out
def _ema(values, period):
    out=[]; current=None; multiplier=Decimal("2")/(period+1)
    for i, value in enumerate(values):
        if i == period - 1: current=_mean(values[:period])
        elif i >= period and current is not None: current=(value-current)*multiplier+current
        out.append(current)
    return out
def _slope(values, i, lookback):
    if i < lookback or values[i] is None or values[i-lookback] in (None, 0): return None
    return _pct(values[i] - values[i-lookback], values[i-lookback])
def _aligned_return(benchmark, bars, i, sessions):
    current=benchmark.get(bars[i]["trading_date"]); prior=benchmark.get(bars[i-sessions]["trading_date"])
    return _pct(current-prior, prior) if current is not None and prior not in (None, 0) else None
def _checksum(bar, trading_date, version):
    return sha256(json.dumps(serialize_value({"bar": bar, "date": trading_date, "version": version}), default=str, sort_keys=True).encode()).hexdigest()


def assign_relative_strength_percentiles(
    rows: Sequence[dict[str, object]], eligible_isins: set[str] | None = None
) -> None:
    """Assign deterministic cross-sectional percentiles; equal scores share rank."""
    eligible = [
        row for row in rows
        if row.get("relative_strength_composite") is not None
        and (eligible_isins is None or row.get("isin") in eligible_isins)
    ]
    values = sorted({_decimal(row["relative_strength_composite"]) for row in eligible})
    denominator = max(1, len(values) - 1)
    for row in eligible:
        score = _decimal(row["relative_strength_composite"])
        row["relative_strength_percentile"] = (Decimal(values.index(score)) / denominator) * 100
