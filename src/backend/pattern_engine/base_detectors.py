"""Primary base-pattern geometry detectors for flat bases, 52-week highs and VCPs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from statistics import median

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import PatternClass, PatternState, SwingType, ZoneType
from pattern_engine.models import DetectionContext, PatternCandidate, PriceZone, SwingPoint


_D = Decimal


class PrimaryBaseService:
    """Runs Phase 9 geometry detectors over one point-in-time security snapshot."""

    def __init__(self, configuration: PatternEngineConfiguration) -> None:
        self._configuration = configuration

    def detect(self, security, bars, features, swings, zones, context) -> list[PatternCandidate]:
        return detect_primary_bases(security, bars, features, swings, zones, context, self._configuration)


def detect_primary_bases(
    security: Mapping[str, object], bars: Sequence[Mapping[str, object]], features: Sequence[Mapping[str, object]],
    swings: Sequence[SwingPoint], zones: Sequence[PriceZone], context: DetectionContext, configuration: PatternEngineConfiguration,
) -> list[PatternCandidate]:
    """Detect base structures using only point-in-time-safe inputs from prior phases."""

    ordered_bars = sorted((b for b in bars if _date(b) <= context.as_of_date), key=_date)
    ordered_features = sorted((f for f in features if _date(f) <= context.as_of_date), key=_date)
    if not ordered_bars or not ordered_features or _date(ordered_bars[-1]) != context.as_of_date:
        return []
    isin = str(security.get("isin") or ordered_bars[-1].get("isin") or "")
    if not isin:
        raise ValueError("Primary base detectors require security.isin")
    feature_by_date = {_date(row): row for row in ordered_features}
    if _date(ordered_features[-1]) != context.as_of_date: return []
    visible_swings = [s for s in swings if s.isin == isin and s.is_meaningful and s.confirmation_date <= context.as_of_date]
    visible_zones = [z for z in zones if z.isin == isin and (z.confirmation_date or z.end_date) <= context.as_of_date]
    result: list[PatternCandidate] = []
    flat = _flat_base(isin, ordered_bars, feature_by_date, visible_zones, context, configuration, visible_swings)
    high = _base_52wh(isin, ordered_bars, feature_by_date, context, configuration)
    vcp = _vcp(isin, ordered_bars, feature_by_date, visible_swings, visible_zones, context, configuration)
    return [candidate for candidate in (flat, high, vcp) if candidate is not None]


def _flat_base(isin, bars, features, zones, context, config, swings=()):
    settings = config.section("flat_base")
    best = None
    for window in _candidate_windows(bars, int(settings["min_duration_sessions"]), int(settings["max_duration_sessions"])):
        resistance = _zone_for(window, zones, ZoneType.RESISTANCE)
        support = _zone_for(window, zones, ZoneType.SUPPORT)
        if resistance is None or support is None or resistance.test_count < 2 or support.test_count < 2: continue
        high, low = max(_decimal(row["high_price"]) for row in window), min(_decimal(row["low_price"]) for row in window)
        depth = _pct(high - low, high)
        if depth is None: continue
        regression_move = _ols_movement([_decimal(row["close_price"]) for row in window])
        atr_ratio = _third_ratio(window, features, "atr_14")
        volume_ratio = _third_volume_ratio(window)
        if regression_move is None: continue
        broken = depth > _decimal(settings["max_depth_pct"]) or regression_move > _decimal(settings["maximum_regression_move_pct"])
        if broken:
            prior = window[:-1]
            if len(prior) < int(settings["min_duration_sessions"]): continue
            prior_high = max(_decimal(b["high_price"]) for b in prior)
            prior_depth = _pct(prior_high - min(_decimal(b["low_price"]) for b in prior), prior_high)
            if prior_depth > _decimal(settings["max_depth_pct"]) or _ols_movement([_decimal(b["close_price"]) for b in prior]) > _decimal(settings["maximum_regression_move_pct"]): continue
        resistance_dispersion = _zone_dispersion(resistance, swings)
        support_dispersion = _zone_dispersion(support, swings)
        pivot, close = resistance.median_price, _decimal(window[-1]["close_price"])
        pivot_distance = _pct(pivot - close, close)
        quality_components = {
            "depth": _score_inverse(depth, _decimal(settings["max_depth_pct"]), _D("20")),
            "resistance_quality": _score_inverse(resistance_dispersion, _D("1.5"), _D("20")),
            "support_quality": _score_inverse(support_dispersion, _D("1.5"), _D("15")),
            "flatness": _score_inverse(regression_move, _decimal(settings["maximum_regression_move_pct"]), _D("15")),
            "atr_compression": _score_inverse(atr_ratio, _D("1"), _D("10")),
            "volume_compression": _score_inverse(volume_ratio, _D("1"), _D("10")),
            "trend_context": _trend_score(features.get(_date(window[-1])), _D("10")),
        }
        quality = sum(quality_components.values(), _D("0"))
        invalid = broken or close < support.median_price * (1 - support.tolerance_pct / 100)
        ready = not invalid and pivot_distance is not None and pivot_distance <= _decimal(settings["ready_pivot_distance_pct"]) and quality >= _decimal(settings["ready_quality_score"])
        state = PatternState.INVALIDATED if invalid else PatternState.READY if ready else PatternState.MATURE if quality >= 65 else PatternState.FORMING
        candidate = _candidate(isin, "BASE-FLAT", window[0], context, state, quality, quality, pivot, support.median_price, support.median_price * (1 - support.tolerance_pct / 100), {
            "duration_sessions": len(window), "base_depth_pct": depth, "resistance_zone_id": resistance.zone_id,
            "resistance_tests": resistance.test_count, "resistance_dispersion_pct": resistance_dispersion,
            "support_zone_id": support.zone_id, "support_tests": support.test_count, "support_dispersion_pct": support_dispersion,
            "regression_move_pct": regression_move, "atr_compression_ratio": atr_ratio, "volume_compression_ratio": volume_ratio,
            "pivot_distance_pct": pivot_distance, "quality_components": quality_components, "invalidation_reason": "depth_or_flatness_break" if broken else "close_below_support_tolerance" if invalid else None,
        })
        best = _prefer(best, candidate)
    return best


def _base_52wh(isin, bars, features, context, config):
    settings = config.section("base_52wh")
    if len(bars) < 253: return None
    previous_high = max(_decimal(row["high_price"]) for row in bars[-253:-1])
    best = None
    for window in _candidate_windows(bars, int(settings["min_duration_sessions"]), int(settings["max_duration_sessions"])):
        close = _decimal(window[-1]["close_price"])
        distance = _pct(previous_high - close, previous_high)
        if distance is None or distance > _decimal(settings["maximum_distance_to_52_week_high_pct"]): continue
        high, low = max(_decimal(row["high_price"]) for row in window), min(_decimal(row["low_price"]) for row in window)
        depth = _pct(high - low, high)
        if depth is None or depth > _decimal(settings["max_depth_pct"]): continue
        near = previous_high * (1 - _decimal(settings["near_high_threshold_pct"]) / 100)
        persistence = _decimal(sum(_decimal(row["close_price"]) >= near for row in window) / len(window))
        if persistence < _decimal(settings["minimum_persistence_ratio"]): continue
        atr_ratio, volume_ratio = _third_ratio(window, features, "atr_14"), _third_volume_ratio(window)
        feature = features.get(_date(window[-1]))
        rs = _value(feature, "relative_strength_percentile")
        components = {
            "proximity": _score_inverse(distance, _decimal(settings["maximum_distance_to_52_week_high_pct"]), _D("25")),
            "persistence": _score_direct(persistence, _decimal(settings["minimum_persistence_ratio"]), _D("20")),
            "depth": _score_inverse(depth, _decimal(settings["max_depth_pct"]), _D("15")),
            "atr_compression": _score_inverse(atr_ratio, _D("1"), _D("10")),
            "volume_compression": _score_inverse(volume_ratio, _D("1"), _D("10")),
            "relative_strength": _score_direct(rs, _D("70"), _D("10")),
            "trend": _trend_score(feature, _D("10")),
        }
        quality = sum(components.values(), _D("0"))
        ready = distance <= _decimal(settings["ready_pivot_distance_pct"]) and quality >= _decimal(settings["ready_quality_score"])
        strong_ready = distance <= _decimal(settings["strong_ready_distance_pct"]) and quality >= _decimal(settings["strong_ready_quality_score"])
        state = PatternState.READY if ready else PatternState.MATURE if quality >= 65 else PatternState.FORMING
        candidate = _candidate(isin, "BASE-52WH", window[0], context, state, quality, quality, previous_high, low, low, {
            "duration_sessions": len(window), "previous_52_week_high": previous_high, "distance_to_52_week_high_pct": distance,
            "base_depth_pct": depth, "near_high_threshold": near, "persistence_ratio": persistence,
            "atr_compression_ratio": atr_ratio, "volume_compression_ratio": volume_ratio, "relative_strength_percentile": rs,
            "quality_components": components, "ready": ready, "strong_ready": strong_ready,
        })
        best = _prefer(best, candidate)
    return best


def _vcp(isin, bars, features, swings, zones, context, config):
    settings = config.section("vcp")
    sequence = _alternating_contractions(swings)
    candidates = []
    for count in range(int(settings["min_contractions"]), min(int(settings["max_contractions"]), len(sequence)) + 1):
        candidate = _vcp_window(isin, bars, features, sequence[-count:], zones, context, config)
        if candidate is not None: candidates.append(candidate)
    return max(candidates, key=lambda c: (c.state is PatternState.INVALIDATED, c.measurements["contraction_count"], c.quality_score), default=None)


def _vcp_window(isin, bars, features, sequence, zones, context, config):
    settings = config.section("vcp")
    by_day = {_date(bar): index for index, bar in enumerate(bars)}
    start_index = by_day.get(sequence[0][0].pivot_date)
    if start_index is None: return None
    window = bars[start_index:]
    if not int(settings["min_duration_sessions"]) <= len(window) <= int(settings["max_duration_sessions"]): return None
    contractions = [_pct(high.price - low.price, high.price) for high, low in sequence]
    if len(contractions) < int(settings["min_contractions"]) or any(value is None or value <= 0 for value in contractions): return None
    expanding = len(contractions) > int(settings["min_contractions"]) and _contractions_progress(contractions[:-1]) and contractions[-1] > contractions[-2] * _D("1.35")
    if not _contractions_progress(contractions) and not expanding: return None
    high, low = max(_decimal(row["high_price"]) for row in window), min(_decimal(row["low_price"]) for row in window)
    depth = _pct(high - low, high)
    if depth is None: return None
    if not _decimal(settings["min_depth_pct"]) <= depth <= _decimal(settings["max_depth_pct"]):
        prior = window[:-1]
        ph = max(_decimal(b["high_price"]) for b in prior)
        pl = min(_decimal(b["low_price"]) for b in prior)
        if not (_decimal(window[-1]["close_price"]) < pl and _decimal(settings["min_depth_pct"]) <= _pct(ph - pl, ph) <= _decimal(settings["max_depth_pct"])): return None
    feature = features.get(_date(window[-1])); atr14 = _value(feature, "atr_14")
    lows = [pair[1] for pair in sequence]
    low_progression = all(lows[index].price >= lows[index - 1].price - (atr14 or _D("0")) * _D("0.5") for index in range(1, len(lows)))
    atr_ratio, volume_ratio = _third_ratio(window, features, "atr_10"), _last_ten_volume_ratio(window)
    final_high = sequence[-1][0]
    pivot_zone = _nearest_resistance(final_high, zones)
    pivot = pivot_zone.median_price if pivot_zone is not None else final_high.price
    close = _decimal(window[-1]["close_price"]); pivot_distance = _pct(pivot - close, close)
    buffer = (pivot_zone.breakout_buffer_pct if pivot_zone is not None else _decimal(config.section("breakout")["breakout_buffer_pct"])) / 100
    structural_low = min(_decimal(row["low_price"]) for row in window[:-1]) if len(window) > 1 else low
    invalid = close < structural_low or (len(contractions) > 1 and contractions[-1] > contractions[-2] * _D("1.35")) or (_value(feature, "sma_50") is not None and close < _value(feature, "sma_50") and (_value(feature, "sma_50_slope") or _D("0")) <= 0)
    triggered = close > pivot * (1 + buffer)
    confirmed = triggered and len(window) >= 2 and sequence[-1][1].confirmation_date <= _date(window[-2]) and all(_decimal(row["close_price"]) > pivot for row in window[-2:])
    progression_score = _D("25") if all(contractions[index] < contractions[index - 1] for index in range(1, len(contractions))) else _D("12.5")
    components = {
        "contraction_progression": progression_score, "atr_compression": _score_inverse(atr_ratio, _D("1"), _D("15")),
        "volume_compression": _score_inverse(volume_ratio, _D("1"), _D("15")), "low_progression": _D("10") if low_progression else _D("0"),
        "pivot_quality": _D("10") if pivot_zone is not None else _D("6"), "base_geometry": _score_range(depth, _D("10"), _D("25"), _D("10")),
        "trend_context": _trend_score(feature, _D("10")), "relative_strength": _score_direct(_value(feature, "relative_strength_percentile"), _D("70"), _D("5")),
    }
    quality = sum(components.values(), _D("0"))
    maturity_components = {
        "contraction_count": _D("25"), "final_contraction": _score_inverse(contractions[-1], _decimal(settings["max_final_contraction_pct"]), _D("20")),
        "atr_compression": _score_inverse(atr_ratio, _D("1"), _D("15")), "volume_compression": _score_inverse(volume_ratio, _D("1"), _D("10")),
        "pivot_defined": _D("15") if pivot else _D("0"), "pivot_proximity": _score_inverse(pivot_distance, _decimal(settings["ready_pivot_distance_pct"]), _D("15")),
    }
    maturity = sum(maturity_components.values(), _D("0"))
    if invalid: state = PatternState.INVALIDATED
    elif confirmed: state = PatternState.CONFIRMED
    elif triggered: state = PatternState.TRIGGERED
    elif maturity >= _decimal(settings["ready_maturity_score"]) and pivot_distance is not None and pivot_distance <= _decimal(settings["ready_pivot_distance_pct"]) and contractions[-1] <= _decimal(settings["max_final_contraction_pct"]): state = PatternState.READY
    elif maturity >= 65: state = PatternState.MATURE
    else: state = PatternState.FORMING
    return _candidate(isin, "BASE-VCP", window[0], context, state, quality, maturity, pivot, structural_low, structural_low, {
        "duration_sessions": len(window), "base_depth_pct": depth, "contraction_count": len(contractions), "contractions_pct": tuple(contractions),
        "contraction_ratios": tuple(contractions[index] / contractions[index - 1] for index in range(1, len(contractions))),
        "final_contraction_pct": contractions[-1], "low_progression": low_progression, "atr_compression_ratio": atr_ratio,
        "volume_compression_ratio": volume_ratio, "pivot_source": "resistance_zone" if pivot_zone else "final_swing_high",
        "pivot_distance_pct": pivot_distance, "quality_components": components, "maturity_components": maturity_components,
        "lifecycle_evidence": {"detected": True, "forming": maturity < 65, "mature": maturity >= 65, "ready": state is PatternState.READY, "triggered": triggered, "confirmed": confirmed},
        "invalidation_reason": "base_low_or_expanding_contraction_or_trend_failure" if invalid else None,
    }, variant=f"VCP-{len(contractions)}C")


def _candidate_windows(bars, minimum, maximum):
    return [bars[-size:] for size in range(minimum, min(maximum, len(bars)) + 1)]
def _zone_for(window, zones, zone_type):
    start, end = _date(window[0]), _date(window[-1])
    matches = [z for z in zones if z.zone_type is zone_type and z.start_date >= start and (z.last_test_date or z.end_date) <= end]
    return max(matches, key=lambda zone: (zone.test_count, -zone.dispersion_pct), default=None)
def _nearest_resistance(swing, zones):
    matches = [
        z for z in zones if z.zone_type is ZoneType.RESISTANCE
        and abs(z.median_price - swing.price) / swing.price * 100 <= z.tolerance_pct
        and (swing.swing_id in z.source_swing_ids or (z.last_test_date or z.end_date) <= swing.pivot_date)
    ]
    return min(matches, key=lambda zone: abs(zone.median_price - swing.price), default=None)
def _alternating_contractions(swings):
    ordered = sorted(swings, key=lambda swing: swing.pivot_date); result = []; index = 0
    while index < len(ordered) - 1:
        if ordered[index].swing_type is SwingType.HIGH and ordered[index + 1].swing_type is SwingType.LOW:
            result.append((ordered[index], ordered[index + 1])); index += 2
        else: index += 1
    return result
def _zone_dispersion(zone, swings):
    values = [s.price for s in swings if s.swing_id in zone.source_swing_ids]
    if len(values) != len(set(zone.source_swing_ids)) or not values: return None
    mean = _mean(values)
    return (sum((value - mean) ** 2 for value in values) / len(values)).sqrt() / mean * 100
def _contractions_progress(values): return all(values[index] <= values[index - 1] * _D("0.90") for index in range(1, len(values)))
def _third_ratio(window, features, field):
    third = len(window) // 3
    if not third: return None
    first = [_value(features.get(_date(row)), field) for row in window[:third]]; last = [_value(features.get(_date(row)), field) for row in window[-third:]]
    first, last = [value for value in first if value is not None], [value for value in last if value is not None]
    return _ratio(_median(last), _median(first))
def _third_volume_ratio(window):
    third = len(window) // 3
    return _ratio(_median([_decimal(row["volume"]) for row in window[-third:]]), _median([_decimal(row["volume"]) for row in window[:third]])) if third else None
def _last_ten_volume_ratio(window): return _ratio(_median([_decimal(row["volume"]) for row in window[-10:]]), _median([_decimal(row["volume"]) for row in window[:max(1, len(window) // 2)]]))
def _ols_movement(values):
    count = len(values); mean_x = _D(count - 1) / 2; mean_y = _mean(values); denominator = sum((_D(index) - mean_x) ** 2 for index in range(count))
    if not denominator or mean_y in (None, 0): return None
    slope = sum((_D(index) - mean_x) * (value - mean_y) for index, value in enumerate(values)) / denominator
    return abs(slope) * count / mean_y * 100
def _trend_score(feature, weight):
    if feature is None: return _D("0")
    return weight if _value(feature, "sma_50") is not None and _value(feature, "sma_200") is not None and _value(feature, "sma_50") > _value(feature, "sma_200") and (_value(feature, "sma_50_slope") or _D("0")) > 0 else _D("0")
def _score_inverse(value, maximum, weight): return _D("0") if value is None else max(_D("0"), min(weight, weight * (1 - value / (maximum * 2))))
def _score_direct(value, threshold, weight): return _D("0") if value is None else max(_D("0"), min(weight, weight * value / threshold))
def _score_range(value, lower, upper, weight): return weight if value is not None and lower <= value <= upper else _D("0")
def _prefer(previous, candidate):
    key = lambda c: (c.state is PatternState.INVALIDATED, c.quality_score or 0)
    return candidate if previous is None or key(candidate) > key(previous) else previous
def _candidate(isin, pattern_type, start, context, state, quality, maturity, pivot, support, invalidation, measurements, *, variant=None):
    return PatternCandidate(isin, PatternClass.BASE, pattern_type, variant, _date(start), context.as_of_date, context.as_of_date, state, quality, maturity, None, None, pivot, support, invalidation, {**measurements, "as_of_date": context.as_of_date}, (pattern_type,), "base_structure_break")
def _date(row):
    value = row["trading_date"]; return value if isinstance(value, date) else date.fromisoformat(str(value))
def _decimal(value): return value if isinstance(value, Decimal) else _D(str(value))
def _value(row, key): return None if row is None or row.get(key) is None else _decimal(row[key])
def _ratio(numerator, denominator): return numerator / denominator if numerator is not None and denominator not in (None, 0) else None
def _pct(value, denominator): return value / denominator * 100 if denominator not in (None, 0) else None
def _mean(values): return sum(values, _D("0")) / len(values) if values else None
def _median(values): return _D(str(median(values))) if values else None
