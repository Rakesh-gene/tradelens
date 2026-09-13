"""One shared, point-in-time-safe breakout core with source adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import PatternClass, PatternState, ZoneType
from pattern_engine.models import DetectionContext, PatternCandidate, PriceZone


_D = Decimal


class BreakoutService:
    def __init__(self, configuration: PatternEngineConfiguration) -> None:
        self._configuration = configuration

    def detect(self, security, bars, features, zones, context, source_bases=()) -> list[PatternCandidate]:
        return detect_breakouts(
            security, bars, features, zones, context, self._configuration, source_bases
        )


def detect_breakouts(
    security: Mapping[str, object], bars: Sequence[Mapping[str, object]], features: Sequence[Mapping[str, object]],
    zones: Sequence[PriceZone], context: DetectionContext, configuration: PatternEngineConfiguration,
    source_bases: Sequence[object] = (),
) -> list[PatternCandidate]:
    bars = sorted((bar for bar in bars if _date(bar) <= context.as_of_date), key=_date)
    features = sorted((row for row in features if _date(row) <= context.as_of_date), key=_date)
    if not bars or not features or _date(bars[-1]) != context.as_of_date or _date(features[-1]) != context.as_of_date:
        return []
    isin = str(security.get("isin") or bars[-1].get("isin") or "")
    if not isin:
        raise ValueError("Breakout detectors require security.isin")
    feature_by_date = {_date(row): row for row in features}
    sources = _sources(isin, bars, zones, source_bases, context, configuration)
    result: list[PatternCandidate] = []
    for source in sources:
        result.extend(_breakout_core(isin, bars, feature_by_date, context, configuration, source))
    return result


def _sources(isin, bars, zones, source_bases, context, config):
    settings = config.section("breakout")
    indices = {_date(bar): index for index, bar in enumerate(bars)}
    sources = []
    for zone in zones:
        if zone.isin != isin or zone.zone_type is not ZoneType.RESISTANCE or (zone.confirmation_date or zone.end_date) > context.as_of_date:
            continue
        tested = zone.last_test_date or zone.end_date
        age = len(bars) - 1 - indices.get(tested, len(bars))
        if zone.test_count >= int(settings["minimum_resistance_tests"]) and int(settings["lookback_min_sessions"]) <= age <= int(settings["lookback_max_sessions"]):
            base = _matching_base(isin, zone.median_price, source_bases, context.as_of_date)
            sources.append(_PivotSource(
                "BRK-RANGE", None, zone.median_price, zone.start_date, zone.test_count,
                _source_quality(zone.test_count, zone.dispersion_pct),
                {
                    "zone_id": zone.zone_id, "zone_tests": zone.test_count,
                    "zone_dispersion_pct": zone.dispersion_pct,
                    "resistance_age_sessions": age,
                },
                available_date=zone.confirmation_date or zone.end_date,
                source_base=base,
            ))
    recent_52wh = _recent_prior_high(bars, 252, settings)
    if recent_52wh is not None:
        trigger_index, prior, pivot = recent_52wh
        sources.append(_PivotSource(
            "BRK-52WH", None, pivot, _date(prior[0]), _near_tests(prior, pivot, _D("0")),
            _D("80"), {"prior_52_week_high": pivot},
            available_date=_date(bars[trigger_index]),
            source_base=_matching_base(isin, pivot, source_bases, context.as_of_date),
        ))
    min_ath = int(settings["ath_minimum_history_sessions"])
    recent_ath = _recent_prior_high(bars, None, settings, minimum_history=min_ath)
    if recent_ath is not None:
        trigger_index, prior, pivot = recent_ath
        sources.append(_PivotSource(
            "BRK-ATH", None, pivot, _date(prior[0]), _near_tests(prior, pivot, _D("0")),
            _D("80"), {"all_time_high": pivot, "history_sessions": len(prior)},
            available_date=_date(bars[trigger_index]),
            source_base=_matching_base(isin, pivot, source_bases, context.as_of_date),
        ))
    tolerance = _decimal(settings["multi_year_tolerance_pct"])
    for sessions, variant in ((504, "BRK-2Y"), (756, "BRK-3Y"), (1260, "BRK-5Y")):
        recent_multi_year = _recent_prior_high(bars, sessions, settings)
        if recent_multi_year is None:
            continue
        trigger_index, prior, pivot = recent_multi_year
        tests = _near_tests(prior, pivot, tolerance)
        sources.append(_PivotSource(
            "BRK-MULTIY", variant, pivot, _date(prior[0]), tests,
            _source_quality(tests, _D("0")),
            {
                "resistance_lookback_sessions": sessions,
                "resistance_age_sessions": _resistance_age(prior, pivot, tolerance),
                "historical_test_count": tests,
            },
            available_date=_date(bars[trigger_index]),
            source_base=_matching_base(isin, pivot, source_bases, context.as_of_date),
        ))
    return sources


def _recent_prior_high(bars, lookback_sessions, settings, *, minimum_history=None):
    """Return a recent breakout and the resistance known on its trigger date.

    A rolling-high pivot belongs to each possible trigger session.  Calculating
    today's pivot and searching all older bars can pair that pivot with an
    unrelated historical close, leaving a years-old signal active today.
    Search only the breakout failure/confirmation window and calculate each
    candidate session's pivot from data strictly before that session.
    """

    required = minimum_history if minimum_history is not None else lookback_sessions
    if required is None or len(bars) < required + 1:
        return None
    observation_sessions = int(settings["failure_window_sessions"]) + 1
    first_index = max(required, len(bars) - observation_sessions)
    buffer_pct = _decimal(settings["breakout_buffer_pct"])
    minimum_pct = _decimal(settings["minimum_close_above_pivot_pct"])
    for trigger_index in range(first_index, len(bars)):
        prior = (
            bars[:trigger_index]
            if lookback_sessions is None
            else bars[trigger_index - lookback_sessions:trigger_index]
        )
        if len(prior) < required:
            continue
        pivot = max(_decimal(row["high_price"]) for row in prior)
        threshold = pivot + max(pivot * buffer_pct / 100, pivot * minimum_pct / 100)
        if _decimal(bars[trigger_index]["close_price"]) > threshold:
            return trigger_index, prior, pivot
    return None


def _breakout_core(isin, bars, feature_by_date, context, config, source):
    settings = config.section("breakout")
    current = bars[-1]
    feature = feature_by_date[_date(current)]
    atr = _value(feature, "atr_14")
    if atr in (None, _D("0")):
        return []
    buffer_pct = _decimal(settings["breakout_buffer_pct"])
    buffer = source.pivot * buffer_pct / 100
    minimum_close = source.pivot * _decimal(settings["minimum_close_above_pivot_pct"]) / 100
    threshold = source.pivot + max(buffer, minimum_close)
    available_index = next(
        (index for index, row in enumerate(bars) if source.available_date is None or _date(row) >= source.available_date),
        len(bars),
    )
    available_index = max(
        available_index,
        len(bars) - int(settings["failure_window_sessions"]) - 1,
    )
    trigger_index = _trigger_index(bars, source.pivot, threshold, available_index)
    if trigger_index is None:
        return []
    trigger = bars[trigger_index]
    trigger_feature = feature_by_date.get(_date(trigger))
    if trigger_feature is None or _value(trigger_feature, "atr_14") in (None, _D("0")):
        return []
    close = _decimal(current["close_price"])
    trigger_close = _decimal(trigger["close_price"])
    failure_threshold = source.pivot - buffer
    sessions_since_trigger = len(bars) - 1 - trigger_index
    failed = sessions_since_trigger <= int(settings["failure_window_sessions"]) and close < failure_threshold
    clv = _value(trigger_feature, "close_location_value") or _clv(trigger)
    volume_ratio = _ratio(_decimal(trigger["volume"]), _value(trigger_feature, "median_volume_20"))
    current_volume_ratio = _ratio(_decimal(current["volume"]), _value(feature, "median_volume_20"))
    magnitude = _ratio(trigger_close - source.pivot, _value(trigger_feature, "atr_14"))
    range_atr = _ratio(
        _decimal(trigger["high_price"]) - _decimal(trigger["low_price"]),
        _value(trigger_feature, "atr_14"),
    )
    extended = close > source.pivot + atr * 2 or close > source.pivot * _D("1.05")
    trigger_magnitude = _ratio(trigger_close - source.pivot, _value(trigger_feature, "atr_14"))
    trigger_clv = _value(trigger_feature, "close_location_value") or _clv(trigger)
    strong_follow = trigger_magnitude is not None and trigger_magnitude >= _decimal(settings["strong_close_atr"]) and trigger_clv >= _decimal(settings["strong_close_clv"]) and sessions_since_trigger >= 1 and not failed
    closes_above = _consecutive_closes_above(bars, source.pivot)
    confirmed = not failed and sessions_since_trigger >= 1 and (closes_above >= 2 or strong_follow)
    state = PatternState.FAILED if failed else PatternState.CONFIRMED if confirmed else PatternState.TRIGGERED
    components = {
        "resistance_quality": source.quality * _D("0.20"),
        "breakout_magnitude": _bounded_score(magnitude, _D("1.5"), _D("15")),
        "volume_expansion": _bounded_score(volume_ratio, _D("2"), _D("20")),
        "closing_strength": _bounded_score(clv, _D("1"), _D("15")),
        "range_atr_expansion": _bounded_score(range_atr, _D("1.5"), _D("10")),
        "source_base_quality": _score_source_quality(source.source_base_quality, _D("10")),
        "trend_rs_context": _context_quality(trigger_feature, context) * _D("0.10"),
    }
    quality = sum(components.values(), _D("0"))
    evidence = {
        **source.measurements, "pivot_source": source.pattern_type, "pivot": source.pivot,
        "source_base_pattern_instance_id": source.source_base_id,
        "source_base_pattern_type": source.source_base_type,
        "source_base_quality": source.source_base_quality,
        "breakout_date": _date(trigger), "sessions_since_trigger": sessions_since_trigger,
        "buffer_pct": buffer_pct, "minimum_close_above_pivot_pct": _decimal(settings["minimum_close_above_pivot_pct"]), "buffered_pivot": threshold, "failure_threshold": failure_threshold,
        "breakout_magnitude_atr": magnitude, "volume_ratio_20": volume_ratio, "clv": clv,
        "range_expansion_atr": range_atr, "extended": extended, "strong_follow_through": strong_follow,
        "consecutive_closes_above_pivot": closes_above, "quality_components": components,
        "as_of_date": context.as_of_date,
    }
    breakout = _candidate(isin, source.pattern_type, source.variant, source.start_date, context, state, quality, source.pivot, evidence)
    if not failed:
        return [breakout]
    trigger_low = _decimal(trigger["low_price"])
    trigger_volume_ratio = _ratio(_decimal(trigger["volume"]), _value(trigger_feature, "median_volume_20"))
    strong_failure = close < trigger_low and current_volume_ratio is not None and current_volume_ratio >= _D("1.3")
    failure = _candidate(isin, "FAIL-BRK", source.pattern_type, source.start_date, context, PatternState.DETECTED, None, source.pivot, {**evidence, "failed_breakout_type": source.pattern_type, "breakout_candle_low": trigger_low, "breakout_candle_volume_ratio_20": trigger_volume_ratio, "failure_volume_ratio_20": current_volume_ratio, "strong_failure": strong_failure})
    return [breakout, failure]


class _PivotSource:
    def __init__(
        self, pattern_type, variant, pivot, start_date, tests, quality, measurements,
        *, available_date=None, source_base=None,
    ):
        self.pattern_type, self.variant, self.pivot, self.start_date = pattern_type, variant, pivot, start_date
        self.tests, self.quality, self.measurements = tests, quality, measurements
        self.available_date = available_date
        self.source_base_id = source_base["id"] if source_base else None
        self.source_base_type = source_base["type"] if source_base else None
        self.source_base_quality = source_base["quality"] if source_base else None


def _trigger_index(bars, pivot, threshold, available_index=0):
    start = None
    for index, bar in enumerate(bars[available_index:], start=available_index):
        close = _decimal(bar["close_price"])
        if close > threshold and start is None:
            start = index
    return start
def _consecutive_closes_above(bars, pivot):
    count = 0
    for bar in reversed(bars):
        if _decimal(bar["close_price"]) > pivot: count += 1
        else: break
    return count
def _near_tests(bars, pivot, tolerance): return sum(abs(_decimal(bar["high_price"]) - pivot) / pivot * 100 <= tolerance for bar in bars)
def _resistance_age(bars, pivot, tolerance):
    last_test = max(
        index for index, bar in enumerate(bars)
        if abs(_decimal(bar["high_price"]) - pivot) / pivot * 100 <= tolerance
    )
    return len(bars) - 1 - last_test
def _matching_base(isin, pivot, sources, as_of):
    matches = []
    for source in sources:
        source_isin = str(_field(source, "isin") or "")
        pattern_type = str(_field(source, "pattern_type") or "")
        state = str(getattr(_field(source, "state"), "value", _field(source, "state") or ""))
        source_pivot = _field(source, "pivot_price")
        source_dates = [
            value for value in (
                _field(source, "detected_date"),
                _field(source, "last_updated_date"),
                _field(source, "confirmation_date"),
            )
            if value is not None
        ]
        if source_isin != isin or not pattern_type.startswith("BASE-") or source_pivot is None:
            continue
        if state in {"FAILED", "INVALIDATED", "EXPIRED"} or any(_as_date(value) > as_of for value in source_dates):
            continue
        distance = abs(_decimal(source_pivot) - pivot) / pivot * 100
        if distance <= _D("2"):
            variant = _field(source, "variant")
            identifier = _field(source, "pattern_instance_id") or (str(variant) if variant else pattern_type)
            matches.append({
                "id": str(identifier), "type": pattern_type,
                "quality": _optional_decimal(_field(source, "quality_score")),
                "distance": distance,
            })
    return min(matches, key=lambda item: item["distance"], default=None)
def _source_quality(tests, dispersion): return max(_D("0"), min(_D("100"), _D("60") + min(_D("30"), _decimal(tests) * _D("10")) - min(_D("30"), dispersion * _D("10"))))
def _context_quality(feature, context):
    rs = _value(feature, "relative_strength_percentile") or _D("0")
    return max(_D("0"), min(_D("100"), rs))
def _bounded_score(value, target, weight): return _D("0") if value is None else max(_D("0"), min(weight, value / target * weight))
def _score_source_quality(value, weight): return _D("0") if value is None else max(_D("0"), min(weight, value / 100 * weight))
def _candidate(isin, pattern_type, variant, start_date, context, state, quality, pivot, measurements):
    return PatternCandidate(isin, PatternClass.FAILURE if pattern_type == "FAIL-BRK" else PatternClass.BREAKOUT, pattern_type, variant, start_date, context.as_of_date, context.as_of_date, state, quality, None, None, None, pivot, None, pivot, measurements, (pattern_type,), "close_below_buffered_pivot" if pattern_type == "FAIL-BRK" else None)
def _date(row):
    value = row["trading_date"]
    return value if isinstance(value, date) else date.fromisoformat(str(value))
def _decimal(value): return value if isinstance(value, Decimal) else _D(str(value))
def _optional_decimal(value): return None if value is None else _decimal(value)
def _field(value, name): return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
def _as_date(value): return value if isinstance(value, date) else date.fromisoformat(str(value))
def _value(row, key): return None if row is None or row.get(key) is None else _decimal(row[key])
def _ratio(a, b): return a / b if a is not None and b not in (None, _D("0")) else None
def _clv(bar):
    high, low, close = _decimal(bar["high_price"]), _decimal(bar["low_price"]), _decimal(bar["close_price"])
    return _D("0.5") if high == low else (close - low) / (high - low)
