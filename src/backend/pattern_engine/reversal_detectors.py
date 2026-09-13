'''Point-in-time classical reversal detectors for completed chart intervals.'''

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import PatternClass, PatternState, SwingType
from pattern_engine.models import DetectionContext, PatternCandidate, SwingPoint
from pattern_engine.swings import detect_swings


_D = Decimal


def aggregate_completed_bars(
    bars: Sequence[Mapping[str, object]], timeframe: str, as_of: date,
) -> list[dict[str, object]]:
    '''Aggregate adjusted daily bars and omit an incomplete current week/month.'''

    ordered = sorted((row for row in bars if _date(row) <= as_of), key=_date)
    if timeframe == '1D':
        return [dict(row) for row in ordered]
    if timeframe not in {'1W', '1M'}:
        raise ValueError('timeframe must be 1D, 1W, or 1M')
    groups: dict[tuple[int, int], list[Mapping[str, object]]] = {}
    for row in ordered:
        value = _date(row)
        key = (
            (value.isocalendar().year, value.isocalendar().week)
            if timeframe == '1W' else (value.year, value.month)
        )
        groups.setdefault(key, []).append(row)
    current_key = (
        (as_of.isocalendar().year, as_of.isocalendar().week)
        if timeframe == '1W' else (as_of.year, as_of.month)
    )
    result = []
    for key, interval in groups.items():
        if key == current_key:
            continue
        first, last = interval[0], interval[-1]
        result.append({
            **dict(last),
            'open_price': first['open_price'],
            'high_price': max(_decimal(row['high_price']) for row in interval),
            'low_price': min(_decimal(row['low_price']) for row in interval),
            'close_price': last['close_price'],
            'volume': sum((_decimal(row.get('volume') or 0) for row in interval), _D('0')),
            'trading_date': _date(last),
        })
    return result


def detect_reversal_patterns(
    security: Mapping[str, object],
    bars: Sequence[Mapping[str, object]],
    swings: Sequence[SwingPoint],
    context: DetectionContext,
    configuration: PatternEngineConfiguration,
    *,
    timeframe: str = '1D',
) -> list[PatternCandidate]:
    interval_bars = aggregate_completed_bars(bars, timeframe, context.as_of_date)
    if len(interval_bars) < 10:
        return []
    visible_swings = (
        [s for s in swings if s.is_meaningful and s.confirmation_date <= context.as_of_date]
        if timeframe == '1D'
        else [s for s in detect_swings(interval_bars, as_of=_date(interval_bars[-1])) if s.is_meaningful]
    )
    visible_swings.sort(key=lambda value: value.pivot_date)
    indices = {_date(row): index for index, row in enumerate(interval_bars)}
    settings = configuration.section('reversal')
    minimum_separation = int(settings['minimum_separation_bars'])
    maximum_bars = int(settings['maximum_pattern_bars'])
    similarity_limit = _decimal(settings['maximum_peak_similarity_pct'])
    minimum_depth = _decimal(settings['minimum_neckline_depth_pct'])
    buffer_pct = _decimal(settings['breakout_buffer_pct'])
    close = _decimal(interval_bars[-1]['close_price'])
    candidates = []
    for first, middle, last in zip(visible_swings, visible_swings[1:], visible_swings[2:]):
        if first.pivot_date not in indices or last.pivot_date not in indices:
            continue
        first_index, last_index = indices[first.pivot_date], indices[last.pivot_date]
        separation = last_index - first_index
        if separation < minimum_separation or separation > maximum_bars:
            continue
        if first.swing_type is SwingType.LOW and middle.swing_type is SwingType.HIGH and last.swing_type is SwingType.LOW:
            candidate = _double_candidate(
                str(security.get('isin') or first.isin), first, middle, last, close,
                context, timeframe, 'REV-DBOT', 'BULLISH', similarity_limit,
                minimum_depth, buffer_pct,
            )
        elif first.swing_type is SwingType.HIGH and middle.swing_type is SwingType.LOW and last.swing_type is SwingType.HIGH:
            candidate = _double_candidate(
                str(security.get('isin') or first.isin), first, middle, last, close,
                context, timeframe, 'REV-DTOP', 'BEARISH', similarity_limit,
                minimum_depth, buffer_pct,
            )
        else:
            candidate = None
        if candidate is not None:
            candidates.append(candidate)
    return candidates[-1:]


def _double_candidate(
    isin, first, middle, last, close, context, timeframe, pattern_type, direction,
    similarity_limit, minimum_depth, buffer_pct,
):
    reference = (first.price + last.price) / 2
    similarity = abs(first.price - last.price) / reference * 100 if reference else _D('100')
    bullish = direction == 'BULLISH'
    depth = (
        (middle.price - reference) / reference * 100
        if bullish else (reference - middle.price) / reference * 100
    )
    if similarity > similarity_limit or depth < minimum_depth:
        return None
    trigger = (
        close >= middle.price * (1 + buffer_pct / 100)
        if bullish else close <= middle.price * (1 - buffer_pct / 100)
    )
    distance = abs(close - middle.price) / middle.price * 100
    quality = _clamp(_D('100') - similarity / similarity_limit * 50 + min(depth, _D('25')) / 25 * 50)
    maturity = _D('100') if trigger else _clamp(_D('100') - distance * 10)
    state = PatternState.TRIGGERED if trigger else PatternState.READY
    return PatternCandidate(
        isin, PatternClass.REVERSAL, pattern_type, None,
        first.pivot_date, context.as_of_date, context.as_of_date, state,
        quality, maturity, None, None, middle.price, reference,
        min(first.price, last.price) if bullish else max(first.price, last.price),
        {
            'first_pivot_date': first.pivot_date,
            'neckline_pivot_date': middle.pivot_date,
            'second_pivot_date': last.pivot_date,
            'peak_similarity_pct': similarity,
            'neckline_depth_pct': depth,
            'distance_to_neckline_pct': distance,
            'breakout_buffer_pct': buffer_pct,
            'as_of_date': context.as_of_date,
        },
        (pattern_type,), 'close_beyond_outer_pivot',
        timeframe, 'REVERSAL', direction, True,
    )


def _date(row):
    value = row['trading_date']
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _decimal(value):
    return value if isinstance(value, Decimal) else _D(str(value))


def _clamp(value):
    return max(_D('0'), min(_D('100'), value))
