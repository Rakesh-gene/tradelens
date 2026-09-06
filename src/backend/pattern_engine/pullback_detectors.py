"""Point-in-time-safe breakout-retest and moving-average pullback detectors."""

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


class PullbackService:
    """Runs the Phase 11 primary pullback detectors for one security snapshot."""

    def __init__(self, configuration: PatternEngineConfiguration) -> None:
        self._configuration = configuration

    def detect(self, security, bars, features, swings, source_breakouts, context) -> list[PatternCandidate]:
        return detect_pullbacks(
            security, bars, features, swings, source_breakouts, context, self._configuration
        )


def detect_pullbacks(
    security: Mapping[str, object],
    bars: Sequence[Mapping[str, object]],
    features: Sequence[Mapping[str, object]],
    swings: Sequence[SwingPoint],
    source_breakouts: Sequence[object],
    context: DetectionContext,
    configuration: PatternEngineConfiguration,
) -> list[PatternCandidate]:
    """Detect pullbacks without consuming observations after the requested as-of date."""

    bars = sorted((row for row in bars if _date(row) <= context.as_of_date), key=_date)
    features = sorted((row for row in features if _date(row) <= context.as_of_date), key=_date)
    if not bars or not features or _date(bars[-1]) != context.as_of_date or _date(features[-1]) != context.as_of_date:
        return []
    isin = str(security.get("isin") or bars[-1].get("isin") or "")
    if not isin:
        raise ValueError("Pullback detectors require security.isin")
    feature_by_date = {_date(row): row for row in features}
    visible_swings = [
        swing for swing in swings
        if swing.isin == isin and swing.is_meaningful and swing.confirmation_date <= context.as_of_date
    ]
    candidates: list[PatternCandidate] = []
    for source in source_breakouts:
        normalized = _source_breakout(source, isin, context.as_of_date)
        if normalized is not None:
            candidate = _breakout_retest(isin, bars, feature_by_date, normalized, context, configuration)
            if candidate is not None:
                candidates.append(candidate)
    for detector in (_ema20_pullback, _sma50_pullback):
        candidate = detector(isin, bars, feature_by_date, visible_swings, context, configuration)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


class _SourceBreakout:
    def __init__(self, instance_id, pattern_type, variant, breakout_date, pivot, quality):
        self.instance_id = instance_id
        self.pattern_type = pattern_type
        self.variant = variant
        self.breakout_date = breakout_date
        self.pivot = pivot
        self.quality = quality


def _source_breakout(source, isin, as_of):
    pattern_type = str(_field(source, "pattern_type") or "")
    state = _field(source, "state")
    source_isin = str(_field(source, "isin") or "")
    instance_id = _field(source, "pattern_instance_id")
    pivot = _field(source, "pivot_price")
    measurements = _field(source, "measurements") or {}
    breakout_date = (
        _field(source, "trigger_date")
        or (measurements.get("breakout_date") if isinstance(measurements, Mapping) else None)
        or _field(source, "detected_date")
    )
    confirmation_date = _field(source, "confirmation_date")
    last_updated_date = _field(source, "last_updated_date")
    if (
        pattern_type not in _BREAKOUT_TYPES
        or str(getattr(state, "value", state)) != PatternState.CONFIRMED.value
        or source_isin != isin
        or not instance_id
        or pivot is None
        or breakout_date is None
        or (confirmation_date is not None and _as_date(confirmation_date) > as_of)
        or (last_updated_date is not None and _as_date(last_updated_date) > as_of)
    ):
        return None
    breakout_date = _as_date(breakout_date)
    if breakout_date > as_of:
        return None
    quality = _field(source, "quality_score")
    return _SourceBreakout(
        str(instance_id), pattern_type, _field(source, "variant"), breakout_date,
        _decimal(pivot), _optional_decimal(quality),
    )


def _breakout_retest(isin, bars, features, source, context, config):
    settings = config.section("breakout_retest")
    indices = {_date(row): index for index, row in enumerate(bars)}
    breakout_index = indices.get(source.breakout_date)
    if breakout_index is None:
        return None
    elapsed = len(bars) - 1 - breakout_index
    if not int(settings["min_sessions_after_breakout"]) <= elapsed <= int(settings["max_sessions_after_breakout"]):
        return None
    current_feature = features.get(context.as_of_date)
    breakout_feature = features.get(source.breakout_date)
    atr = _value(breakout_feature, "atr_14")
    natr = _value(current_feature, "natr_14")
    if atr in (None, 0) or natr is None:
        return None
    post_breakout = bars[breakout_index + 1:-1]
    if not post_breakout:
        return None
    peak_index = max(
        range(breakout_index + 1, len(bars) - 1),
        key=lambda index: _decimal(bars[index]["high_price"]),
    )
    peak = _decimal(bars[peak_index]["high_price"])
    advance_pct = _pct(peak - source.pivot, source.pivot)
    advance_atr = _ratio(peak - source.pivot, atr)
    if (
        advance_pct is None
        or advance_atr is None
        or advance_pct < _decimal(settings["minimum_advance_pct"])
        or advance_atr < _decimal(settings["minimum_advance_atr"])
    ):
        return None
    pullback = bars[peak_index + 1:]
    tolerance = _clamp(
        natr * _decimal(settings["retest_tolerance_natr_factor"]),
        _decimal(settings["minimum_retest_tolerance_pct"]),
        _decimal(settings["maximum_retest_tolerance_pct"]),
    )
    lower = source.pivot * (1 - tolerance / 100)
    upper = source.pivot * (1 + tolerance / 100)
    earliest_touch_index = breakout_index + int(settings["min_sessions_after_breakout"])
    touch_indices = [
        index for index in range(max(peak_index + 1, earliest_touch_index), len(bars))
        if lower <= _decimal(bars[index]["low_price"]) <= upper
    ]
    touch_index = touch_indices[0] if touch_indices else None
    retest_session = touch_index - breakout_index if touch_index is not None else None
    pullback_volume_ratio = _ratio(
        _median([_decimal(row["volume"]) for row in pullback]),
        _value(current_feature, "median_volume_20"),
    )
    close = _decimal(bars[-1]["close_price"])
    two_below = len(bars) >= 2 and all(_decimal(row["close_price"]) < lower for row in bars[-2:])
    invalid = two_below or close < source.pivot - atr
    trigger_level = None
    triggered = False
    if touch_index is not None and touch_index < len(bars) - 1:
        retest_swing_highs = [_decimal(row["high_price"]) for row in bars[touch_index:-1]]
        if retest_swing_highs:
            trigger_level = max(retest_swing_highs) * (1 + _decimal(settings["reclaim_buffer_pct"]) / 100)
            triggered = close > trigger_level
    state = (
        PatternState.INVALIDATED if invalid else
        PatternState.TRIGGERED if triggered else
        PatternState.READY if touch_index is not None else
        PatternState.FORMING
    )
    proximity = min(
        (abs(_decimal(row["low_price"]) - source.pivot) / source.pivot * 100 for row in pullback),
        default=None,
    )
    depth = _pct(peak - min(_decimal(row["low_price"]) for row in pullback), peak)
    clv = _value(current_feature, "close_location_value") or _clv(bars[-1])
    rs = _value(current_feature, "relative_strength_percentile")
    components = {
        "original_breakout_quality": _score_direct(source.quality, _D("100"), _D("20")),
        "retest_proximity": _score_inverse(proximity, tolerance, _D("20")),
        "pullback_volume": _score_inverse(pullback_volume_ratio, _D("1"), _D("20")),
        "retest_depth": _score_inverse(depth, _decimal(settings["max_retest_depth_pct"]), _D("15")),
        "bounce_closing_behavior": _score_direct(clv, _D("0.70"), _D("10")),
        "relative_strength_retention": _score_direct(rs, _D("70"), _D("10")),
        "retest_timing": (
            _D("5")
            if retest_session is not None
            and int(settings["preferred_min_sessions"]) <= retest_session <= int(settings["preferred_max_sessions"])
            else _D("2.5")
        ),
    }
    return _candidate(
        isin, "PB-BRKRET", None, source.breakout_date, context, state, sum(components.values(), _D("0")),
        trigger_level or source.pivot, source.pivot, lower,
        {
            "source_pattern_instance_id": source.instance_id,
            "source_pattern_type": source.pattern_type,
            "source_pattern_variant": source.variant,
            "original_pivot": source.pivot,
            "original_breakout_date": source.breakout_date,
            "original_breakout_quality": source.quality,
            "sessions_after_breakout": elapsed,
            "retest_session_after_breakout": retest_session,
            "maximum_advance_pct": advance_pct,
            "maximum_advance_atr": advance_atr,
            "retest_tolerance_pct": tolerance,
            "retest_zone_lower": lower,
            "retest_zone_upper": upper,
            "retest_touch_date": _date(bars[touch_index]) if touch_index is not None else None,
            "retest_volume_ratio": pullback_volume_ratio,
            "retest_depth_pct": depth,
            "trigger_level": trigger_level,
            "quality_components": components,
            "invalidation_reason": "two_closes_below_retest_zone" if two_below else "close_below_pivot_minus_atr" if invalid else None,
        },
        (source.instance_id, source.pattern_type),
        "two_closes_below_retest_tolerance_or_close_below_pivot_minus_atr",
    )


def _ema20_pullback(isin, bars, features, swings, context, config):
    settings = config.section("ema20_pullback")
    candidate_window = _ma_window(bars, features, swings, "ema_20", settings)
    if candidate_window is None:
        return None
    high, high_index, pullback, depth = candidate_window
    prerequisite = features.get(_date(bars[high_index]))
    if not _ema_alignment(prerequisite, settings):
        return None
    prior = bars[max(0, high_index - int(settings["prior_close_lookback_sessions"])):high_index]
    if len(prior) < int(settings["prior_close_lookback_sessions"]):
        return None
    closes_above = sum(
        _value(features.get(_date(row)), "ema_20") is not None
        and _decimal(row["close_price"]) > _value(features.get(_date(row)), "ema_20")
        for row in prior
    )
    if closes_above < int(settings["minimum_prior_closes_above"]):
        return None
    return _moving_average_candidate(
        isin, "PB-EMA20", None, bars, features, swings, context, settings,
        high, high_index, pullback, depth, "ema_20", "ema_20_slope", closes_above, len(prior),
    )


def _sma50_pullback(isin, bars, features, swings, context, config):
    settings = config.section("sma50_pullback")
    candidate_window = _ma_window(bars, features, swings, "sma_50", settings)
    if candidate_window is None:
        return None
    high, high_index, pullback, depth = candidate_window
    prerequisite = features.get(_date(bars[high_index]))
    sma50, sma200 = _value(prerequisite, "sma_50"), _value(prerequisite, "sma_200")
    slope = _value(prerequisite, "sma_50_slope")
    if sma50 is None or sma200 is None or slope is None or sma50 <= sma200 or slope <= _decimal(settings["minimum_sma_slope_pct"]):
        return None
    prior = bars[max(0, high_index - int(settings["prior_close_lookback_sessions"])):high_index]
    if len(prior) < int(settings["prior_close_lookback_sessions"]):
        return None
    closes_above = sum(
        _value(features.get(_date(row)), "sma_50") is not None
        and _decimal(row["close_price"]) > _value(features.get(_date(row)), "sma_50")
        for row in prior
    )
    ratio = _D(closes_above) / len(prior)
    if ratio < _decimal(settings["minimum_prior_closes_above_ratio"]):
        return None
    touch_count = _touch_episode_count(bars, features, "sma_50", settings)
    variant = "PB-SMA50-T1" if touch_count <= 1 else "PB-SMA50-T2" if touch_count == 2 else "PB-SMA50-T3+"
    return _moving_average_candidate(
        isin, "PB-SMA50", variant, bars, features, swings, context, settings,
        high, high_index, pullback, depth, "sma_50", "sma_50_slope", closes_above, len(prior),
        touch_count=touch_count,
    )


def _ma_window(bars, features, swings, ma_field, settings):
    indices = {_date(row): index for index, row in enumerate(bars)}
    maximum = int(settings["max_duration_sessions"])
    highs = sorted(
        (swing for swing in swings if swing.swing_type is SwingType.HIGH and swing.pivot_date in indices),
        key=lambda swing: swing.pivot_date,
        reverse=True,
    )
    for high in highs:
        high_index = indices[high.pivot_date]
        duration = len(bars) - 1 - high_index
        if not int(settings["min_duration_sessions"]) <= duration <= maximum:
            continue
        pullback = bars[high_index + 1:]
        depth = _pct(high.price - min(_decimal(row["low_price"]) for row in pullback), high.price)
        if depth is not None and _decimal(settings["min_depth_pct"]) <= depth <= _decimal(settings["max_depth_pct"]):
            return high, high_index, pullback, depth
    return None


def _moving_average_candidate(
    isin, pattern_type, variant, bars, features, swings, context, settings,
    high, high_index, pullback, depth, ma_field, slope_field, closes_above, prior_count,
    *, touch_count=None,
):
    touch_indices = []
    for index in range(high_index + 1, len(bars)):
        feature = features.get(_date(bars[index]))
        ma = _value(feature, ma_field)
        tolerance = _touch_tolerance(feature, settings)
        if ma is not None and tolerance is not None and ma * (1 - tolerance / 100) <= _decimal(bars[index]["low_price"]) <= ma * (1 + tolerance / 100):
            touch_indices.append(index)
    if not touch_indices:
        return None
    first_touch = touch_indices[0]
    current = bars[-1]
    current_feature = features.get(context.as_of_date)
    ma = _value(current_feature, ma_field)
    atr = _value(current_feature, "atr_14")
    slope = _value(current_feature, slope_field)
    if ma is None or atr in (None, 0):
        return None
    trigger_level = max((_decimal(row["high_price"]) for row in bars[-3:-1]), default=None)
    triggered = first_touch < len(bars) - 1 and trigger_level is not None and _decimal(current["close_price"]) > trigger_level
    structural_low = _recent_structural_low(swings, context.as_of_date)
    if pattern_type == "PB-EMA20":
        below = len(bars) >= 2 and all(
            _value(features.get(_date(row)), ma_field) is not None
            and _decimal(row["close_price"]) < _value(features.get(_date(row)), ma_field)
            for row in bars[-2:]
        )
        penetration = _decimal(current["close_price"]) < ma - atr
        invalid = below and penetration or structural_low is not None and _decimal(current["close_price"]) < structural_low.price
    else:
        significant = len(bars) >= 2 and all(
            _value(features.get(_date(row)), ma_field) is not None
            and _value(features.get(_date(row)), "atr_14") is not None
            and _decimal(row["close_price"]) < _value(features.get(_date(row)), ma_field) - _value(features.get(_date(row)), "atr_14")
            for row in bars[-2:]
        )
        structural_failure = slope is not None and slope <= 0 and structural_low is not None and _decimal(current["close_price"]) < structural_low.price
        invalid = significant or structural_failure
    clv = _value(current_feature, "close_location_value") or _clv(current)
    ready = _decimal(current["close_price"]) >= ma and clv >= _decimal(settings["preferred_clv"])
    state = PatternState.INVALIDATED if invalid else PatternState.TRIGGERED if triggered else PatternState.READY if ready else PatternState.FORMING
    volume_ratio = _ratio(
        _median([_decimal(row["volume"]) for row in bars[high_index + 1:first_touch + 1]]),
        _value(current_feature, "median_volume_20"),
    )
    proximity = min(
        (
            abs(_decimal(row["low_price"]) - _value(features.get(_date(row)), ma_field))
            / _value(features.get(_date(row)), ma_field) * 100
            for row in pullback if _value(features.get(_date(row)), ma_field) not in (None, 0)
        ),
        default=None,
    )
    rs = _value(current_feature, "relative_strength_percentile")
    duration = len(bars) - 1 - high_index
    prerequisite_feature = features.get(_date(bars[high_index]))
    trend_prerequisites = {
        "ema_20": _value(prerequisite_feature, "ema_20"),
        "sma_50": _value(prerequisite_feature, "sma_50"),
        "sma_200": _value(prerequisite_feature, "sma_200"),
        "ema_20_slope": _value(prerequisite_feature, "ema_20_slope"),
        "sma_50_slope": _value(prerequisite_feature, "sma_50_slope"),
    }
    if pattern_type == "PB-EMA20":
        components = {
            "trend_quality": _D("25"),
            "ema20_proximity": _score_inverse(proximity, _decimal(settings["maximum_touch_tolerance_pct"]), _D("15")),
            "pullback_depth": _score_range(depth, _decimal(settings["min_depth_pct"]), _decimal(settings["max_depth_pct"]), _D("15")),
            "pullback_volume": _score_inverse(volume_ratio, _D("1"), _D("15")),
            "pullback_duration": _score_range(_D(duration), _D(settings["min_duration_sessions"]), _D(settings["max_duration_sessions"]), _D("10")),
            "closing_behavior": _score_direct(clv, _D("0.60"), _D("10")),
            "relative_strength_retention": _score_direct(rs, _D("70"), _D("10")),
        }
    else:
        components = {
            "trend_quality": _D("25"),
            "sma50_slope": _score_direct(slope, _D("0.1"), _D("15")),
            "touch_quality": _score_inverse(proximity, _decimal(settings["maximum_touch_tolerance_pct"]), _D("15")),
            "pullback_volume": _score_inverse(volume_ratio, _D("1"), _D("15")),
            "pullback_depth": _score_range(depth, _decimal(settings["min_depth_pct"]), _decimal(settings["max_depth_pct"]), _D("10")),
            "bounce_strength": _score_direct(clv, _D("0.60"), _D("10")),
            "relative_strength_retention": _score_direct(rs, _D("70"), _D("10")),
        }
    supporting = tuple(dict.fromkeys(context.supporting_pattern_identifiers))
    return _candidate(
        isin, pattern_type, variant, high.pivot_date, context, state, sum(components.values(), _D("0")),
        trigger_level, ma, structural_low.price if structural_low is not None else ma - atr,
        {
            "source_swing_id": high.swing_id,
            "source_swing_high": high.price,
            "pullback_depth_pct": depth,
            "pullback_duration_sessions": duration,
            "touch_date": _date(bars[first_touch]),
            "touch_tolerance_pct": _touch_tolerance(features.get(_date(bars[first_touch])), settings),
            "pullback_volume_ratio": volume_ratio,
            "prior_closes_above_ma": closes_above,
            "prior_close_observations": prior_count,
            "trend_prerequisites": trend_prerequisites,
            "touch_episode_count": touch_count,
            "trigger_level": trigger_level,
            "clv": clv,
            "quality_components": components,
            "invalidation_reason": "persistent_ma_penetration_or_structural_low_break" if invalid else None,
        },
        supporting,
        "persistent_significant_ma_penetration_or_structural_low_break",
    )


def _touch_episode_count(bars, features, ma_field, settings):
    lookback = int(settings["touch_count_lookback_sessions"])
    separation = int(settings["touch_episode_separation_sessions"])
    start = max(0, len(bars) - lookback)
    episodes: list[int] = []
    in_touch = False
    for index in range(start, len(bars)):
        feature = features.get(_date(bars[index]))
        ma, tolerance = _value(feature, ma_field), _touch_tolerance(feature, settings)
        if ma is None or tolerance is None:
            in_touch = False
            continue
        low = _decimal(bars[index]["low_price"])
        touching = ma * (1 - tolerance / 100) <= low <= ma * (1 + tolerance / 100)
        if touching and not in_touch and (not episodes or index - episodes[-1] >= separation):
            episodes.append(index)
        in_touch = touching
    return len(episodes)


def _touch_tolerance(feature, settings):
    natr = _value(feature, "natr_14")
    if natr is None:
        return None
    return _clamp(
        natr * _decimal(settings["touch_tolerance_natr_factor"]),
        _decimal(settings["minimum_touch_tolerance_pct"]),
        _decimal(settings["maximum_touch_tolerance_pct"]),
    )


def _ema_alignment(feature, settings):
    ema20, sma50, sma200 = _value(feature, "ema_20"), _value(feature, "sma_50"), _value(feature, "sma_200")
    ema_slope, sma_slope = _value(feature, "ema_20_slope"), _value(feature, "sma_50_slope")
    minimum = _decimal(settings["minimum_ema_slope_pct"])
    return None not in (ema20, sma50, sma200, ema_slope, sma_slope) and ema20 > sma50 > sma200 and ema_slope > minimum and sma_slope > 0


def _recent_structural_low(swings, as_of):
    return max(
        (swing for swing in swings if swing.swing_type is SwingType.LOW and swing.confirmation_date <= as_of),
        key=lambda swing: swing.pivot_date,
        default=None,
    )


def _candidate(isin, pattern_type, variant, start, context, state, quality, pivot, support, invalidation, measurements, supporting, rule):
    return PatternCandidate(
        isin, PatternClass.PULLBACK, pattern_type, variant, start, context.as_of_date,
        context.as_of_date, state, quality, None, None, None, pivot, support, invalidation,
        {**measurements, "as_of_date": context.as_of_date}, supporting, rule,
    )


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
def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))
def _clv(bar):
    high, low, close = _decimal(bar["high_price"]), _decimal(bar["low_price"]), _decimal(bar["close_price"])
    return _D("0.5") if high == low else (close - low) / (high - low)
def _score_inverse(value, maximum, weight):
    return _D("0") if value is None or maximum <= 0 else max(_D("0"), min(weight, weight * (1 - value / (maximum * 2))))
def _score_direct(value, threshold, weight):
    return _D("0") if value is None or threshold <= 0 else max(_D("0"), min(weight, weight * value / threshold))
def _score_range(value, lower, upper, weight):
    return weight if value is not None and lower <= value <= upper else _D("0")
