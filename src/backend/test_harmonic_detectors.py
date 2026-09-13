from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import PatternState, SwingType
from pattern_engine.harmonic_detectors import detect_harmonic_patterns
from pattern_engine.models import DetectionContext, SwingPoint


_ISIN = 'INE000000001'


def _swing(day, confirmation, kind, price):
    return SwingPoint(
        None, _ISIN, date(2026, 1, day), date(2026, 1, confirmation),
        kind, Decimal(price), None, Decimal('10'), True,
    )


class HarmonicDetectorTestCase(unittest.TestCase):
    def test_abcd_requires_measured_leg_and_retracement_ratios(self):
        configuration = load_pattern_engine_configuration()
        bars = [{
            'isin': _ISIN, 'trading_date': date(2026, 1, 1) + timedelta(days=index),
            'open_price': Decimal('110'), 'high_price': Decimal('115'),
            'low_price': Decimal('90'), 'close_price': Decimal('113'),
            'volume': Decimal('1000'),
        } for index in range(15)]
        swings = (
            _swing(2, 5, SwingType.HIGH, '120'),
            _swing(6, 9, SwingType.LOW, '100'),
            _swing(10, 12, SwingType.HIGH, '112'),
            _swing(12, 15, SwingType.LOW, '92'),
        )
        context = DetectionContext(date(2026, 1, 15), {}, None, (), configuration.version)

        candidate = detect_harmonic_patterns(
            {'isin': _ISIN}, bars, swings, context, configuration,
        )[0]

        self.assertEqual('HARM-ABCD', candidate.pattern_type)
        self.assertEqual(PatternState.TRIGGERED, candidate.state)
        self.assertEqual(('HARMONIC', 'BULLISH'), (
            candidate.pattern_group, candidate.direction,
        ))
        self.assertEqual(Decimal('1'), candidate.measurements['cd_to_ab_ratio'])
        self.assertEqual(Decimal('0.6'), candidate.measurements['bc_to_ab_retracement'])


if __name__ == '__main__':
    unittest.main()
