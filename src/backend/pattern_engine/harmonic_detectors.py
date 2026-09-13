'''Measured, point-in-time harmonic detectors for completed intervals.'''

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import PatternClass, PatternState, SwingType
from pattern_engine.models import DetectionContext, PatternCandidate, SwingPoint
from pattern_engine.reversal_detectors import aggregate_completed_bars
from pattern_engine.swings import detect_swings


_D = Decimal


def detect_harmonic_patterns(
    security: Mapping[str, object], bars: Sequence[Mapping[str, object]],
    swings: Sequence[SwingPoint], context: DetectionContext,
    configuration: PatternEngineConfiguration, *, timeframe='1D',
) -> list[PatternCandidate]:
    interval_bars = aggregate_completed_bars(bars, timeframe, context.as_of_date)
    if len(interval_bars) < 10:
        return []
    visible = (
        [s for s in swings if s.is_meaningful and s.confirmation_date <= context.as_of_date]
        if timeframe == '1D'
        else [s for s in detect_swings(interval_bars, as_of=interval_bars[-1]['trading_date']) if s.is_meaningful]
    )
    visible.sort(key=lambda value: value.pivot_date)
    settings = configuration.section('harmonic')
    minimum_leg = _decimal(settings['abcd_leg_ratio_min'])
    maximum_leg = _decimal(settings['abcd_leg_ratio_max'])
    minimum_retracement = _decimal(settings['abcd_retracement_min'])
    maximum_retracement = _decimal(settings['abcd_retracement_max'])
    buffer_pct = _decimal(settings['breakout_buffer_pct'])
    close = _decimal(interval_bars[-1]['close_price'])
    candidates = []
    for a, b, c, d in zip(visible, visible[1:], visible[2:], visible[3:]):
        if len({a.swing_type, b.swing_type, c.swing_type, d.swing_type}) != 2:
            continue
        if not (a.swing_type is c.swing_type and b.swing_type is d.swing_type):
            continue
        ab = abs(b.price - a.price)
        bc = abs(c.price - b.price)
        cd = abs(d.price - c.price)
        if ab == 0:
            continue
        leg_ratio, retracement = cd / ab, bc / ab
        if not minimum_leg <= leg_ratio <= maximum_leg:
            continue
        if not minimum_retracement <= retracement <= maximum_retracement:
            continue
        bullish = d.swing_type is SwingType.LOW
        trigger_level = c.price
        triggered = (
            close >= trigger_level * (1 + buffer_pct / 100)
            if bullish else close <= trigger_level * (1 - buffer_pct / 100)
        )
        quality = _clamp(
            _D('100')
            - abs(_D('1') - leg_ratio) * 200
            - abs(_D('0.618') - retracement) * 50
        )
        candidates.append(PatternCandidate(
            str(security.get('isin') or a.isin), PatternClass.HARMONIC,
            'HARM-ABCD', None, a.pivot_date, context.as_of_date,
            context.as_of_date, PatternState.TRIGGERED if triggered else PatternState.READY,
            quality, _D('100') if triggered else _D('80'), None, None,
            trigger_level, d.price, d.price, {
                'a_date': a.pivot_date, 'b_date': b.pivot_date,
                'c_date': c.pivot_date, 'd_date': d.pivot_date,
                'ab_size': ab, 'bc_size': bc, 'cd_size': cd,
                'cd_to_ab_ratio': leg_ratio,
                'bc_to_ab_retracement': retracement,
                'breakout_buffer_pct': buffer_pct,
                'as_of_date': context.as_of_date,
            }, ('HARM-ABCD',), 'close_beyond_point_d',
            timeframe, 'HARMONIC', 'BULLISH' if bullish else 'BEARISH', True,
        ))
    return candidates[-1:]


def _decimal(value):
    return value if isinstance(value, Decimal) else _D(str(value))


def _clamp(value):
    return max(_D('0'), min(_D('100'), value))
