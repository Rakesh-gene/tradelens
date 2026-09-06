"""Independent point-in-time failure-pattern evidence detectors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from statistics import median

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import PatternClass, PatternState, SwingType
from pattern_engine.models import DetectionContext, PatternCandidate, SwingPoint


_D = Decimal
_BREAKOUT_TYPES = frozenset({"BRK-RANGE", "BRK-BASE", "BRK-52WH", "BRK-ATH", "BRK-MULTIY"})


class FailurePatternService:
    """Runs all Phase 12 failure detectors over one immutable as-of snapshot."""

    def __init__(self, configuration: PatternEngineConfiguration) -> None:
        self._configuration = configuration

    def detect(self, security, bars, features, swings, source_patterns, context) -> list[PatternCandidate]:
        return detect_failures(
            security, bars, features, swings, source_patterns, context, self._configuration
        )


def detect_failures(
    security: Mapping[str, object],
    bars: Sequence[Mapping[str, object]],
    features: Sequence[Mapping[str, object]],
    swings: Sequence[SwingPoint],
    source_patterns: Sequence[object],
    context: DetectionContext,
    configuration: PatternEngineConfiguration,
) -> list[PatternCandidate]:
    """Return failure evidence without changing a source pattern's lifecycle."""

    bars = sorted((row for row in bars if _date(row) <= context.as_of_date), key=_date)
    features = sorted((row for row in features if _date(row) <= context.as_of_date), key=_date)
    if not bars or not features or _date(bars[-1]) != context.as_of_date or _date(features[-1]) != context.as_of_date:
        return []
    isin = str(security.get("isin") or bars[-1].get("isin") or "")
    if not isin:
        raise ValueError("Failure detectors require security.isin")
    feature_by_date = {_date(row): row for row in features}
    visible_swings = [
        swing for swing in swings
        if swing.isin == isin and swing.is_meaningful
        and swing.confirmation_date <= context.as_of_date
    ]
    sources = [
        source for source in (
            _normalize_source(value, isin, context.as_of_date)
            for value in source_patterns
        )
        if source is not None
    ]
    result: list[PatternCandidate] = []
    for source in (item for item in sources if item.pattern_type in _BREAKOUT_TYPES):
        candidate = _failed_breakout(isin, bars, feature_by_date, source, context, configuration)
        if candidate is not None:
            result.append(candidate)
    for source in (item for item in sources if item.pattern_type.startswith("BASE-")):
        candidate = _failed_base(isin, bars, feature_by_date, source, context, configuration)
        if candidate is not None:
            result.append(candidate)
    ema_source = _latest_source(sources, {"PB-EMA20"})
    ema_failure = _failed_ema20(
        isin, bars, feature_by_date, visible_swings, ema_source, context, configuration
    )
    if ema_failure is not None:
        result.append(ema_failure)
    sma_source = _latest_source(sources, {"PB-SMA50"})
    sma_failure = _failed_sma50(
        isin, bars, feature_by_date, sma_source, context, configuration
    )
    if sma_failure is not None:
        result.append(sma_failure)
    trend_source = _latest_source(sources, {"TREND-HHHL", "TREND-S2", "TREND-MA"})
    structural_failure = _failed_structure(
        isin, bars, feature_by_date, visible_swings, trend_source, context, configuration
    )
    if structural_failure is not None:
        result.append(structural_failure)
    return result


class _Source:
    def __init__(
        self, instance_id, pattern_type, variant, state, start_date, detected_date,
        pivot, support, invalidation, quality, measurements,
    ):
        self.instance_id = instance_id
        self.pattern_type = pattern_type
        self.variant = variant
        self.state = state
        self.start_date = start_date
        self.detected_date = detected_date
        self.pivot = pivot
        self.support = support
        self.invalidation = invalidation
        self.quality = quality
        self.measurements = measurements


def _normalize_source(source, isin, as_of):
    source_isin = str(_field(source, "isin") or "")
    pattern_type = str(_field(source, "pattern_type") or "")
    if source_isin != isin or not pattern_type:
        return None
    dates = [
        value for value in (
            _field(source, "detected_date"),
            _field(source, "last_updated_date"),
            _field(source, "confirmation_date"),
        )
        if value is not None
    ]
    if any(_as_date(value) > as_of for value in dates):
        return None
    measurements = _field(source, "measurements")
    if not isinstance(measurements, Mapping):
        measurements = {}
    start_date = _field(source, "start_date") or _field(source, "detected_date") or as_of
    detected_date = _field(source, "detected_date") or start_date
    state = _field(source, "state")
    return _Source(
        str(_field(source, "pattern_instance_id")) if _field(source, "pattern_instance_id") else None,
        pattern_type,
        _field(source, "variant"),
        str(getattr(state, "value", state)) if state is not None else None,
        _as_date(start_date),
        _as_date(detected_date),
        _optional_decimal(_field(source, "pivot_price")),
        _optional_decimal(_field(source, "support_price")),
        _optional_decimal(_field(source, "invalidation_price")),
        _optional_decimal(_field(source, "quality_score")),
        measurements,
    )


def _failed_breakout(isin, bars, features, source, context, config):
    if source.state is not None and source.state not in {
        PatternState.TRIGGERED.value,
        PatternState.CONFIRMED.value,
        PatternState.FAILED.value,
    }:
        return None
    pivot = source.pivot or _measurement_decimal(source, "original_pivot") or _measurement_decimal(source, "pivot")
    breakout_date = _measurement_date(source, "breakout_date") or _measurement_date(source, "original_breakout_date") or source.detected_date
    indices = {_date(row): index for index, row in enumerate(bars)}
    breakout_index = indices.get(breakout_date)
    if pivot is None or breakout_index is None:
        return None
    elapsed = len(bars) - 1 - breakout_index
    settings = config.section("failure")
    if elapsed < 0 or elapsed > int(settings["breakout_failure_window_sessions"]):
        return None
    buffer_pct = _decimal(config.section("breakout")["breakout_buffer_pct"])
    failure_threshold = pivot * (1 - buffer_pct / 100)
    close = _decimal(bars[-1]["close_price"])
    if close >= failure_threshold:
        return None
    current_feature = features.get(context.as_of_date)
    breakout_feature = features.get(breakout_date)
    current_volume_ratio = _volume_ratio(bars[-1], current_feature)
    breakout_low = _decimal(bars[breakout_index]["low_price"])
    post_breakout = bars[breakout_index:]
    highest = max(_decimal(row["high_price"]) for row in post_breakout)
    maximum_advance = max(_D("0"), highest - pivot)
    maximum_advance_pct = _pct(maximum_advance, pivot)
    breakout_atr = _value(breakout_feature, "atr_14")
    days_above = sum(_decimal(row["close_price"]) > pivot for row in post_breakout)
    distance_below = _pct(pivot - close, pivot)
    rs_deterioration = _deterioration(
        _value(breakout_feature, "relative_strength_percentile"),
        _value(current_feature, "relative_strength_percentile"),
    )
    close_below_breakout = close < breakout_low
    strong_failure = (
        close_below_breakout
        and current_volume_ratio is not None
        and current_volume_ratio >= _decimal(settings["breakout_strong_failure_volume_ratio"])
    )
    return _candidate(
        isin, "FAIL-BRK", source.pattern_type, breakout_date, context,
        pivot, pivot, failure_threshold, source,
        {
            "original_pivot": pivot,
            "original_breakout_date": breakout_date,
            "highest_advance_after_breakout": highest,
            "maximum_advance_amount": maximum_advance,
            "maximum_advance_pct": maximum_advance_pct,
            "maximum_advance_atr": _ratio(maximum_advance, breakout_atr),
            "days_above_pivot": days_above,
            "sessions_since_breakout": elapsed,
            "distance_below_pivot_pct": distance_below,
            "failure_depth_pct": distance_below,
            "failure_volume_ratio": current_volume_ratio,
            "breakout_candle_low": breakout_low,
            "close_below_breakout_candle": close_below_breakout,
            "relative_strength_at_breakout": _value(breakout_feature, "relative_strength_percentile"),
            "relative_strength_at_failure": _value(current_feature, "relative_strength_percentile"),
            "rs_deterioration": rs_deterioration,
            "strong_failure": strong_failure,
        },
        "close_below_buffered_breakout_pivot",
    )


def _failed_base(isin, bars, features, source, context, config):
    support = source.support or _measurement_decimal(source, "support_level")
    if support is None:
        return None
    threshold = source.invalidation
    if threshold is not None:
        tolerance = _pct(support - threshold, support)
    else:
        tolerance = _measurement_decimal(source, "support_tolerance_pct")
        if tolerance is None:
            tolerance = _decimal(config.section("failure")["base_support_break_pct"])
        threshold = support * (1 - tolerance / 100)
    close = _decimal(bars[-1]["close_price"])
    if close >= threshold:
        return None
    feature = features.get(context.as_of_date)
    sma50 = _value(feature, "sma_50")
    penetration = _pct(support - close, support)
    return _candidate(
        isin, "FAIL-BASE", source.pattern_type, source.start_date, context,
        source.pivot, support, threshold, source,
        {
            "support_level": support,
            "support_tolerance_pct": tolerance,
            "support_failure_threshold": threshold,
            "support_penetration_pct": penetration,
            "volume_ratio_20": _volume_ratio(bars[-1], feature),
            "trend_score": _trend_score(feature),
            "distance_below_sma50_pct": _pct(sma50 - close, sma50) if sma50 is not None and close < sma50 else _D("0"),
        },
        "close_below_base_support_tolerance",
    )


def _failed_ema20(isin, bars, features, swings, source, context, config):
    settings = config.section("failure")
    required = int(settings["ema20_minimum_consecutive_closes"])
    days_below = _consecutive_days_below(bars, features, "ema_20")
    if days_below < required:
        return None
    run = bars[-days_below:]
    penetrations = _penetrations_atr(run, features, "ema_20")
    maximum_penetration = max(penetrations, default=None)
    structural_low = _latest_swing_low(bars, swings, context, config)
    close = _decimal(bars[-1]["close_price"])
    swing_broken = structural_low is not None and close < structural_low.price
    if (
        (maximum_penetration is None or maximum_penetration <= _decimal(settings["ema20_minimum_penetration_atr"]))
        and not swing_broken
    ):
        return None
    feature = features.get(context.as_of_date)
    return _candidate(
        isin, "FAIL-EMA20", source.pattern_type if source else None,
        source.start_date if source else _date(run[0]), context,
        _value(feature, "ema_20"), structural_low.price if structural_low else None,
        structural_low.price if swing_broken else _value(feature, "ema_20") - (_value(feature, "atr_14") or _D("0")),
        source,
        {
            "days_below_ema20": days_below,
            "maximum_penetration_atr": maximum_penetration,
            "median_failure_volume": _median([_decimal(row["volume"]) for row in run]),
            "volume_during_failure_ratio": _ratio(
                _median([_decimal(row["volume"]) for row in run]),
                _value(feature, "median_volume_20"),
            ),
            "previous_trend_quality": source.quality if source else None,
            "broken_swing_low": structural_low.price if swing_broken else None,
            "swing_low_broken": swing_broken,
        },
        "two_closes_below_ema20_and_atr_penetration_or_swing_low_break",
    )


def _failed_sma50(isin, bars, features, source, context, config):
    settings = config.section("failure")
    required = int(settings["sma50_minimum_consecutive_closes"])
    days_below = _consecutive_days_below(bars, features, "sma_50")
    if days_below < required:
        return None
    run = bars[-days_below:]
    penetrations = _penetrations_atr(run, features, "sma_50")
    maximum_penetration = max(penetrations, default=None)
    if maximum_penetration is None or maximum_penetration < _decimal(settings["sma50_minimum_penetration_atr"]):
        return None
    current = bars[-1]
    feature = features.get(context.as_of_date)
    close = _decimal(current["close_price"])
    sma50 = _value(feature, "sma_50")
    slope = _value(feature, "sma_50_slope")
    return _candidate(
        isin, "FAIL-SMA50", source.pattern_type if source else None,
        source.start_date if source else _date(run[0]), context,
        sma50, sma50, sma50 - (_value(feature, "atr_14") or _D("0")) if sma50 is not None else None,
        source,
        {
            "break_pct": _pct(sma50 - close, sma50) if sma50 is not None else None,
            "break_atr": _ratio(sma50 - close, _value(feature, "atr_14")) if sma50 is not None else None,
            "maximum_penetration_atr": maximum_penetration,
            "volume_expansion": _volume_ratio(current, feature),
            "sma50_slope": slope,
            "days_below": days_below,
            "failed_reclaim_count": _failed_reclaims(
                bars, features, "sma_50", source.start_date if source else None
            ),
            "stronger_failure": slope is not None and slope <= 0,
        },
        "two_closes_below_sma50_with_at_least_one_atr_penetration",
    )


def _failed_structure(isin, bars, features, swings, source, context, config):
    structural_low = _latest_swing_low(bars, swings, context, config)
    if structural_low is None:
        return None
    close = _decimal(bars[-1]["close_price"])
    if close >= structural_low.price:
        return None
    feature = features.get(context.as_of_date)
    swing_feature = features.get(structural_low.pivot_date)
    atr = _value(feature, "atr_14")
    indices = {_date(row): index for index, row in enumerate(bars)}
    trend_start = source.start_date if source is not None and source.start_date in indices else structural_low.pivot_date
    age = len(bars) - 1 - indices[trend_start]
    return _candidate(
        isin, "FAIL-STRUCT", source.pattern_type if source else None,
        source.start_date if source else structural_low.pivot_date, context,
        structural_low.price, structural_low.price, structural_low.price, source,
        {
            "broken_swing_id": structural_low.swing_id,
            "broken_swing_low": structural_low.price,
            "broken_swing_date": structural_low.pivot_date,
            "break_pct": _pct(structural_low.price - close, structural_low.price),
            "break_atr": _ratio(structural_low.price - close, atr),
            "volume_ratio_20": _volume_ratio(bars[-1], feature),
            "rs_deterioration": _deterioration(
                _value(swing_feature, "relative_strength_percentile"),
                _value(feature, "relative_strength_percentile"),
            ),
            "trend_age_sessions": age,
        },
        "close_below_previous_confirmed_meaningful_swing_low",
    )


def _latest_swing_low(bars, swings, context, config):
    indices = {_date(row): index for index, row in enumerate(bars)}
    lookback = int(config.section("failure")["structural_failure_lookback_sessions"])
    minimum_index = max(0, len(bars) - 1 - lookback)
    return max(
        (
            swing for swing in swings
            if swing.swing_type is SwingType.LOW
            and swing.pivot_date in indices
            and indices[swing.pivot_date] >= minimum_index
            and swing.confirmation_date <= context.as_of_date
        ),
        key=lambda swing: swing.pivot_date,
        default=None,
    )


def _latest_source(sources, pattern_types):
    return max(
        (source for source in sources if source.pattern_type in pattern_types),
        key=lambda source: (source.detected_date, source.start_date),
        default=None,
    )


def _consecutive_days_below(bars, features, ma_field):
    count = 0
    for row in reversed(bars):
        ma = _value(features.get(_date(row)), ma_field)
        if ma is None or _decimal(row["close_price"]) >= ma:
            break
        count += 1
    return count


def _penetrations_atr(rows, features, ma_field):
    result = []
    for row in rows:
        feature = features.get(_date(row))
        ma, atr = _value(feature, ma_field), _value(feature, "atr_14")
        if ma is not None and atr not in (None, 0):
            result.append((ma - _decimal(row["close_price"])) / atr)
    return result


def _failed_reclaims(bars, features, ma_field, start_date=None):
    attempts = 0
    was_below = False
    visible = [row for row in bars if start_date is None or _date(row) >= start_date]
    for row in visible:
        ma = _value(features.get(_date(row)), ma_field)
        if ma is None:
            continue
        below = _decimal(row["close_price"]) < ma
        if below and not was_below:
            attempts += 1
        was_below = below
    return max(0, attempts - 1)


def _candidate(isin, pattern_type, variant, start, context, pivot, support, invalidation, source, measurements, rule):
    source_identifiers = ()
    source_measurements = {
        "source_pattern_instance_id": None,
        "source_pattern_type": None,
        "source_pattern_variant": None,
        "source_pattern_state": None,
    }
    if source is not None:
        source_identifiers = tuple(
            value for value in (source.instance_id, source.pattern_type) if value
        )
        source_measurements = {
            "source_pattern_instance_id": source.instance_id,
            "source_pattern_type": source.pattern_type,
            "source_pattern_variant": source.variant,
            "source_pattern_state": source.state,
        }
    return PatternCandidate(
        isin, PatternClass.FAILURE, pattern_type, variant, start, context.as_of_date,
        context.as_of_date, PatternState.DETECTED, None, None, None, None,
        pivot, support, invalidation,
        {**source_measurements, **measurements, "as_of_date": context.as_of_date},
        source_identifiers, rule,
    )


def _trend_score(feature):
    if feature is None:
        return None
    close = _value(feature, "close_price")
    ema20, sma50, sma200 = _value(feature, "ema_20"), _value(feature, "sma_50"), _value(feature, "sma_200")
    conditions = [
        ema20 is not None and sma50 is not None and ema20 > sma50,
        sma50 is not None and sma200 is not None and sma50 > sma200,
        (_value(feature, "ema_20_slope") or _D("0")) > 0,
        (_value(feature, "sma_50_slope") or _D("0")) > 0,
    ]
    if close is not None and ema20 is not None:
        conditions.append(close > ema20)
    return _D(sum(conditions)) / len(conditions) * 100


def _measurement_decimal(source, key):
    return _optional_decimal(source.measurements.get(key))
def _measurement_date(source, key):
    value = source.measurements.get(key)
    return None if value is None else _as_date(value)
def _volume_ratio(bar, feature):
    direct = _value(feature, "volume_ratio_20")
    return direct if direct is not None else _ratio(_decimal(bar["volume"]), _value(feature, "median_volume_20"))
def _deterioration(previous, current):
    return max(_D("0"), previous - current) if previous is not None and current is not None else None
def _field(value, name):
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
def _date(row):
    return _as_date(row["trading_date"])
def _as_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))
def _decimal(value):
    return value if isinstance(value, Decimal) else _D(str(value))
def _optional_decimal(value):
    return None if value is None else _decimal(value)
def _value(row, key):
    return None if row is None or row.get(key) is None else _decimal(row[key])
def _ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator not in (None, 0) else None
def _pct(value, denominator):
    return value / denominator * 100 if denominator not in (None, 0) else None
def _median(values):
    return _D(str(median(values))) if values else None
