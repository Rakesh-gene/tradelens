"""Reusable supporting-pattern detectors built only from prior engine stages.

The module deliberately contains no persistence or HTTP concerns.  A caller
supplies adjusted bars, precomputed feature rows, confirmed swings/zones and
point-in-time context; each detector returns independently auditable evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Protocol

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import PatternClass, PatternState, SwingType
from pattern_engine.models import DetectionContext, PatternCandidate, PriceZone, SwingPoint


_D = Decimal


class SupportingPatternDetector(Protocol):
    def detect(
        self, security: Mapping[str, object], bars: Sequence[Mapping[str, object]],
        features: Sequence[Mapping[str, object]], swings: Sequence[SwingPoint],
        zones: Sequence[PriceZone], context: DetectionContext,
    ) -> list[PatternCandidate]: ...


class SupportingPatternService:
    """Runs the Phase 8 detectors against one security/as-of snapshot."""

    def __init__(self, configuration: PatternEngineConfiguration) -> None:
        self._configuration = configuration

    def detect(
        self, security: Mapping[str, object], bars: Sequence[Mapping[str, object]],
        features: Sequence[Mapping[str, object]], swings: Sequence[SwingPoint],
        zones: Sequence[PriceZone], context: DetectionContext,
    ) -> list[PatternCandidate]:
        return detect_supporting_patterns(security, bars, features, swings, zones, context, self._configuration)


def detect_supporting_patterns(
    security: Mapping[str, object], bars: Sequence[Mapping[str, object]],
    features: Sequence[Mapping[str, object]], swings: Sequence[SwingPoint],
    zones: Sequence[PriceZone], context: DetectionContext, configuration: PatternEngineConfiguration,
) -> list[PatternCandidate]:
    """Return all true supporting candidates without recalculating stored features."""

    ordered_bars = sorted((b for b in bars if _date_from_row(b) <= context.as_of_date), key=_date_from_row)
    ordered_features = sorted((f for f in features if _date_from_row(f) <= context.as_of_date), key=_date_from_row)
    if not ordered_bars or not ordered_features:
        return []
    as_of = context.as_of_date
    if _date_from_row(ordered_bars[-1]) != as_of or _date_from_row(ordered_features[-1]) != as_of:
        return []
    isin = str(security.get("isin") or ordered_bars[-1].get("isin") or "")
    if not isin:
        raise ValueError("Supporting detectors require security.isin")
    current = ordered_features[-1]
    candidates: list[PatternCandidate] = []
    candidates += _base_tight(isin, ordered_bars, current, context, configuration)
    candidates += _trend_hhhl(isin, ordered_bars, swings, context, configuration)
    candidates += _trend_s2(isin, ordered_bars, current, context, configuration)
    candidates += _trend_ma(isin, ordered_bars[-1], current, context, configuration)
    candidates += _comp_nr7(isin, ordered_bars, context, configuration)
    candidates += _comp_ib(isin, ordered_bars, context, configuration)
    candidates += _comp_atr(isin, ordered_features, context, configuration)
    candidates += _comp_range(isin, current, context, configuration)
    candidates += _mom_acc(isin, current, context)
    candidates += _mom_rsl(isin, current, context, configuration)
    candidates += _mom_rsb(isin, ordered_bars, context, configuration)
    candidates += _vol_dry(isin, current, context, configuration)
    candidates += _vol_exp(isin, ordered_bars[-1], current, context, configuration)
    return candidates


def _base_tight(isin, bars, feature, context, configuration):
    metrics = _metrics(feature, "range_10", "atr_5", "atr_20", "median_volume_5", "median_volume_20")
    if len(bars) < 10 or any(value is None for value in metrics.values()): return []
    closes = [_decimal(bar["close_price"]) for bar in bars[-10:]]
    highs, lows = [_decimal(bar["high_price"]) for bar in bars[-10:]], [_decimal(bar["low_price"]) for bar in bars[-10:]]
    close_dispersion = (max(closes) - min(closes)) / max(closes) * 100 if max(closes) else None
    inside_count = sum(highs[index] <= highs[index - 1] and lows[index] >= lows[index - 1] for index in range(1, len(highs)))
    atr_ratio, volume_ratio = _ratio(metrics["atr_5"], metrics["atr_20"]), _ratio(metrics["median_volume_5"], metrics["median_volume_20"])
    max_range, max_atr = _decimal(configuration.section("compression")["maximum_range_pct"]), _decimal(configuration.section("compression")["maximum_atr_ratio"])
    if metrics["range_10"] > max_range or atr_ratio is None or atr_ratio > max_atr or volume_ratio is None or volume_ratio > _D("1"):
        return []
    return [_candidate(isin, PatternClass.BASE, "BASE-TIGHT", bars[-10], context, {**metrics, "atr_5_to_20": atr_ratio, "volume_5_to_20": volume_ratio, "close_dispersion_pct": close_dispersion, "inside_bar_count": inside_count})]


def _trend_hhhl(isin, bars, swings, context, configuration):
    sessions = {_date_from_row(bar): i for i, bar in enumerate(bars)}
    visible = sorted((s for s in swings if s.isin == isin and s.is_meaningful and s.confirmation_date <= context.as_of_date and s.pivot_date in sessions), key=lambda s: s.pivot_date)
    highs, lows = [s for s in visible if s.swing_type is SwingType.HIGH], [s for s in visible if s.swing_type is SwingType.LOW]
    pair_count = min(len(highs), len(lows)) - 1
    required = int(configuration.section("trend")["minimum_higher_high_low_pairs"])
    if pair_count < required: return []
    higher_high = sum(highs[index].price > highs[index - 1].price for index in range(1, len(highs))) / (len(highs) - 1)
    higher_low = sum(lows[index].price > lows[index - 1].price for index in range(1, len(lows))) / (len(lows) - 1)
    pairs = [(a, b) for a, b in zip(visible, visible[1:]) if a.swing_type is SwingType.HIGH and b.swing_type is SwingType.LOW]
    pullbacks = [(a.price - b.price) / a.price * 100 for a, b in pairs]
    durations = [sessions[b.pivot_date] - sessions[a.pivot_date] for a, b in pairs]
    if higher_high < 1 or higher_low < 1: return []
    return [_candidate(isin, PatternClass.TREND, "TREND-HHHL", {"trading_date": visible[0].pivot_date}, context, {
        "higher_high_ratio": _decimal(higher_high), "higher_low_ratio": _decimal(higher_low),
        "trend_duration_sessions": sessions[visible[-1].pivot_date] - sessions[visible[0].pivot_date],
        "average_pullback_depth_pct": _mean(pullbacks), "average_pullback_duration_sessions": _mean(durations),
        "normalized_slope_pct": (visible[-1].price - visible[0].price) / visible[0].price * 100,
    })]


def _trend_s2(isin, bars, feature, context, configuration):
    weekly = {}
    for bar in bars:
        weekly[_date_from_row(bar).isocalendar()[:2]] = bar
    weekly_bars = list(weekly.values())
    if len(weekly_bars) < 34: return []
    closes = [_decimal(bar["close_price"]) for bar in bars]
    weekly_closes = [_decimal(bar["close_price"]) for bar in weekly_bars]
    week30, prior_week30 = _mean(weekly_closes[-30:]), _mean(weekly_closes[-34:-4])
    metrics = _metrics(feature, "sma_50", "sma_200", "sma_50_slope", "sma_200_slope", "range_position_52_week", "relative_strength_percentile")
    if any(value is None for value in metrics.values()): return []
    if not (closes[-1] > week30 and closes[-1] > metrics["sma_50"] and week30 > prior_week30 and metrics["sma_50"] > metrics["sma_200"] and metrics["sma_50_slope"] > 0 and metrics["sma_200_slope"] >= 0): return []
    return [_candidate(isin, PatternClass.TREND, "TREND-S2", weekly_bars[-34], context, {**metrics, "close": closes[-1], "ma_30_week": week30, "ma_30_week_slope_pct": _pct(week30 - prior_week30, prior_week30), "distance_above_30_week_ma_pct": _pct(closes[-1]-week30, week30)})]


def _trend_ma(isin, bar, feature, context, configuration):
    metrics = _metrics(feature, "ema_20", "sma_50", "sma_100", "sma_200", "ema_20_slope", "sma_50_slope", "sma_200_slope")
    close = _value(bar, "close_price")
    if close is None or any(value is None for value in metrics.values()): return []
    rules = dict(zip(("close_above_ema20", "ema20_above_sma50", "sma50_above_sma100", "sma100_above_sma200", "ema20_rising", "sma50_rising", "sma200_nonnegative"),
        (close > metrics["ema_20"], metrics["ema_20"] > metrics["sma_50"], metrics["sma_50"] > metrics["sma_100"], metrics["sma_100"] > metrics["sma_200"], metrics["ema_20_slope"] > 0, metrics["sma_50_slope"] > 0, metrics["sma_200_slope"] >= 0)))
    selected = configuration.section('trend').get('ma_conditions', tuple(rules))
    if not selected or any(key not in rules for key in selected): raise ValueError('Unknown or empty MA conditions')
    conditions = tuple(rules[key] for key in selected)
    score = _D(sum(conditions)) / len(conditions) * 100
    if score == 0: return []
    return [_candidate(isin, PatternClass.TREND, "TREND-MA", feature, context, {**metrics, "close": close, "condition_score": score, "conditions": {key: rules[key] for key in selected}}, quality=score)]


def _comp_nr7(isin, bars, context, configuration):
    lookback = int(configuration.section("compression")["nr7_lookback_sessions"])
    if len(bars) < lookback: return []
    ranges = [_pct(_decimal(bar["high_price"]) - _decimal(bar["low_price"]), _decimal(bar["close_price"])) for bar in bars[-lookback:]]
    if any(value is None for value in ranges): return []
    if ranges[-1] != min(ranges): return []
    return [_candidate(isin, PatternClass.COMPRESSION, "COMP-NR7", bars[-lookback], context, {"daily_range_pct": ranges[-1], "inclusive_window_ranges_pct": tuple(ranges), "window_sessions": lookback})]


def _comp_ib(isin, bars, context, configuration):
    maximum = int(configuration.section("compression")["inside_bar_max_depth"])
    if len(bars) < 2: return []
    depth = 0
    for index in range(len(bars) - 1, 0, -1):
        child, mother = bars[index], bars[index - 1]
        if _decimal(child["high_price"]) <= _decimal(mother["high_price"]) and _decimal(child["low_price"]) >= _decimal(mother["low_price"]): depth += 1
        else: break
        if depth == maximum: break
    if not depth: return []
    mother_range = _decimal(bars[-depth - 1]["high_price"]) - _decimal(bars[-depth - 1]["low_price"])
    current_range = _decimal(bars[-1]["high_price"]) - _decimal(bars[-1]["low_price"])
    return [_candidate(isin, PatternClass.COMPRESSION, "COMP-IB", bars[-depth - 1], context, {"inside_bar_count": depth, "mother_high": _decimal(bars[-depth - 1]["high_price"]), "mother_low": _decimal(bars[-depth - 1]["low_price"]), "compression_ratio": _ratio(current_range, mother_range)}, variant=f"COMP-IB{depth}")]


def _comp_atr(isin, features, context, configuration):
    current = features[-1]; metrics = _metrics(current, "atr_5", "atr_10", "atr_20", "atr_50")
    if len(features) < 252 or any(value is None for value in metrics.values()): return []
    ratio5, ratio10 = _ratio(metrics["atr_5"], metrics["atr_20"]), _ratio(metrics["atr_10"], metrics["atr_50"])
    atrs = [_value(row, "atr_14") for row in features[-252:] if _value(row, "atr_14") is not None]
    if ratio5 is None or ratio10 is None or len(atrs) < 252: return []
    percentile = _decimal(sum(value <= _value(current, "atr_14") for value in atrs) / len(atrs) * 100)
    if ratio5 > _decimal(configuration.section("compression")["maximum_atr_ratio"]): return []
    return [_candidate(isin, PatternClass.COMPRESSION, "COMP-ATR", features[-252], context, {**metrics, "atr_5_to_20": ratio5, "atr_10_to_50": ratio10, "atr_percentile_1_year": percentile})]


def _comp_range(isin, feature, context, configuration):
    metrics = _metrics(feature, "range_5", "range_10", "range_20", "range_50")
    if any(value is None for value in metrics.values()): return []
    ratio5, ratio10 = _ratio(metrics["range_5"], metrics["range_20"]), _ratio(metrics["range_10"], metrics["range_50"])
    maximum = _decimal(configuration.section("compression")["maximum_atr_ratio"])
    if ratio5 is None or ratio10 is None or ratio5 > maximum or ratio10 > maximum: return []
    return [_candidate(isin, PatternClass.COMPRESSION, "COMP-RANGE", feature, context, {**metrics, "range_5_to_20": ratio5, "range_10_to_50": ratio10})]


def _mom_acc(isin, feature, context):
    metrics = _metrics(feature, "return_1_month", "return_3_month", "return_6_month", "return_12_month")
    if any(value is None for value in metrics.values()): return []
    paces = (metrics["return_1_month"], metrics["return_3_month"] / 3, metrics["return_6_month"] / 6, metrics["return_12_month"] / 12)
    components = tuple(max(_D(0), min(_D(1), (a - b) / max(abs(b), _D(1)))) * 100 / 3 for a, b in zip(paces, paces[1:]))
    score = sum(components, _D(0))
    if score == 0: return []
    return [_candidate(isin, PatternClass.MOMENTUM, "MOM-ACC", feature, context, {**metrics, "monthly_pace_1m": paces[0], "monthly_pace_3m": paces[1], "monthly_pace_6m": paces[2], "monthly_pace_12m": paces[3], "acceleration_score": score, "score_components": components}, quality=score)]


def _mom_rsl(isin, feature, context, configuration):
    secondary = feature.get("secondary_metrics") or {}
    metrics = {f"rs_{h}_percentile": _value(secondary, f"rs_{h}_percentile") for h in ("1m", "3m", "6m", "12m")}
    if any(value is None for value in metrics.values()): return []
    components = {h: metrics[f"rs_{h}_percentile"] * weight for h, weight in zip(("1m", "3m", "6m", "12m"), map(_D, ("0.10", "0.25", "0.35", "0.30")))}
    composite = sum(components.values(), _D(0))
    if composite < _decimal(configuration.section("momentum")["minimum_relative_strength_percentile"]): return []
    metrics.update(relative_strength_composite=composite, score_components=components)
    return [_candidate(isin, PatternClass.MOMENTUM, "MOM-RSL", feature, context, metrics)]


def _mom_rsb(isin, bars, context, configuration):
    series = context.benchmark_snapshot.get("bars", ())
    benchmark = {_date_from_row(row): _value(row, "close_price") for row in series if isinstance(row, Mapping) and _date_from_row(row) <= context.as_of_date}
    ratios = [_ratio(_value(bar, "close_price"), benchmark.get(_date_from_row(bar))) for bar in bars]
    result = []
    for period in (20, 50, 252):
        window = ratios[-period:]
        if len(window) < period or any(value is None for value in window): continue
        if window[-1] < max(window): continue
        result.append(_candidate(isin, PatternClass.MOMENTUM, "MOM-RSB", bars[-period], context,
            {"relative_price": window[-1], "relative_price_high": max(window), "window_sessions": period,
             "rs_slope_pct": _pct(window[-1] - window[0], window[0])}, variant=f"RS-{period}D-HIGH"))
    return result


def _vol_dry(isin, feature, context, configuration):
    metrics = _metrics(feature, "median_volume_5", "median_volume_50")
    ratio = _ratio(metrics["median_volume_5"], metrics["median_volume_50"])
    if ratio is None or ratio > _decimal(configuration.section("volume")["maximum_dry_up_ratio"]): return []
    return [_candidate(isin, PatternClass.COMPRESSION, "VOL-DRY", feature, context, {**metrics, "volume_5_to_50": ratio, "strength_band": _band(ratio, ("VERY_STRONG", _D("0.55")), ("STRONG", _D("0.75")), ("MODERATE", _D("0.90")))})]


def _vol_exp(isin, bar, feature, context, configuration):
    median_volume = _value(feature, "median_volume_20")
    volume = _value(bar, "volume")
    ratio = _ratio(volume, median_volume)
    if ratio is None or ratio < _decimal(configuration.section("volume")["minimum_expansion_ratio"]): return []
    band = "VERY_STRONG" if ratio >= _D("2") else "STRONG" if ratio >= _D("1.3") else "MILD"
    return [_candidate(isin, PatternClass.MOMENTUM, "VOL-EXP", feature, context, {"current_volume": volume, "median_volume_20": median_volume, "volume_ratio_20": ratio, "strength_band": band})]


def _candidate(isin, pattern_class, pattern_type, start, context, measurements, *, variant=None, quality=None):
    start_date = _date_from_row(start)
    delivery = {key: _value(start, key) for key in ("delivery_percentage", "median_delivery_percentage_5", "median_delivery_percentage_20", "delivery_expansion_ratio") if _value(start, key) is not None}
    return PatternCandidate(isin, pattern_class, pattern_type, variant, start_date, context.as_of_date, context.as_of_date, PatternState.DETECTED, quality, None, None, None, None, None, None, {**measurements, **delivery, "as_of_date": context.as_of_date}, (pattern_type,), None)


def _date_from_row(row):
    value = row["trading_date"]
    return value if isinstance(value, date) else date.fromisoformat(str(value))
def _decimal(value): return value if isinstance(value, Decimal) else _D(str(value))
def _value(row, key): return None if row.get(key) is None else _decimal(row[key])
def _metrics(row, *keys): return {key: _value(row, key) for key in keys}
def _ratio(numerator, denominator): return numerator / denominator if numerator is not None and denominator not in (None, 0) else None
def _pct(value, denominator): return value / denominator * 100 if denominator not in (None, 0) else None
def _mean(values): return sum((_decimal(value) for value in values), _D("0")) / len(values) if values else None
def _band(value, *bands):
    return next((name for name, threshold in bands if value <= threshold), bands[-1][0])
