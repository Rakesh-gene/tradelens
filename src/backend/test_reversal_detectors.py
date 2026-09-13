from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import PatternState, SwingType
from pattern_engine.models import DetectionContext, SwingPoint
from pattern_engine.reversal_detectors import aggregate_completed_bars, detect_reversal_patterns


_ISIN = 'INE000000001'


def _bars(count=15, *, start=date(2026, 1, 1), close='110'):
    return [
        {
            'isin': _ISIN,
            'trading_date': start + timedelta(days=index),
            'open_price': Decimal('108'),
            'high_price': Decimal('112'),
            'low_price': Decimal('106'),
            'close_price': Decimal(close if index == count - 1 else '110'),
            'volume': Decimal('1000'),
        }
        for index in range(count)
    ]


def _swing(day, confirmation, swing_type, price):
    return SwingPoint(
        None, _ISIN, date(2026, 1, day), date(2026, 1, confirmation),
        swing_type, Decimal(price), None, Decimal('10'), True,
    )


class ReversalDetectorTestCase(unittest.TestCase):
    def setUp(self):
        self.configuration = load_pattern_engine_configuration()

    def test_double_bottom_is_point_in_time_and_emits_explainable_metadata(self):
        bars = _bars(close='122')
        swings = (
            _swing(2, 5, SwingType.LOW, '100'),
            _swing(7, 10, SwingType.HIGH, '120'),
            _swing(11, 14, SwingType.LOW, '101'),
        )
        context = DetectionContext(date(2026, 1, 15), {}, None, (), self.configuration.version)

        candidates = detect_reversal_patterns(
            {'isin': _ISIN}, bars, swings, context, self.configuration,
        )

        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertEqual('REV-DBOT', candidate.pattern_type)
        self.assertEqual(PatternState.TRIGGERED, candidate.state)
        self.assertEqual(('1D', 'REVERSAL', 'BULLISH'), (
            candidate.timeframe, candidate.pattern_group, candidate.direction,
        ))
        self.assertIn('peak_similarity_pct', candidate.measurements)
        self.assertIn('neckline_depth_pct', candidate.measurements)

    def test_double_top_remains_ready_until_neckline_breaks(self):
        bars = _bars(close='100')
        swings = (
            _swing(2, 5, SwingType.HIGH, '120'),
            _swing(7, 10, SwingType.LOW, '100'),
            _swing(11, 14, SwingType.HIGH, '121'),
        )
        context = DetectionContext(date(2026, 1, 15), {}, None, (), self.configuration.version)

        candidate = detect_reversal_patterns(
            {'isin': _ISIN}, bars, swings, context, self.configuration,
        )[0]

        self.assertEqual('REV-DTOP', candidate.pattern_type)
        self.assertEqual(PatternState.READY, candidate.state)
        self.assertEqual('BEARISH', candidate.direction)

    def test_weekly_aggregation_excludes_the_open_week(self):
        bars = _bars(15)
        aggregated = aggregate_completed_bars(bars, '1W', date(2026, 1, 15))

        self.assertTrue(aggregated)
        self.assertLess(aggregated[-1]['trading_date'], date(2026, 1, 12))
        self.assertEqual(sum(row['volume'] for row in bars[:4]), aggregated[0]['volume'])


if __name__ == '__main__':
    unittest.main()
