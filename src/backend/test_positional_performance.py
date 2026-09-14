from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.positional_performance import calculate_positional_performance, preferred_forward_return


class PositionalPerformanceTest(unittest.TestCase):
    def test_reports_three_six_and_twelve_month_trading_horizons(self):
        signal = date(2025, 1, 1)
        bars = [{"trading_date": signal + timedelta(days=index + 1), "open_price": Decimal("100"), "high_price": Decimal(100 + index + 2), "low_price": Decimal("90"), "close_price": Decimal(100 + index + 1)} for index in range(252)]
        result = calculate_positional_performance(signal_date=signal, bars=bars)
        self.assertEqual(signal + timedelta(days=1), result["entryDate"])
        self.assertEqual(Decimal("63"), result["horizons"]["3M"]["returnPct"])
        self.assertEqual(252, result["horizons"]["1Y"]["availableSessions"])
        self.assertTrue(result["horizons"]["1Y"]["complete"])
        self.assertEqual(result["horizons"]["1Y"]["returnPct"], preferred_forward_return(result))

    def test_incomplete_horizon_is_explicit_but_reports_performance_to_date(self):
        signal = date(2025, 1, 1)
        bars = [{"trading_date": signal + timedelta(days=index + 1), "open_price": 100, "high_price": 110, "low_price": 95, "close_price": 105} for index in range(20)]
        result = calculate_positional_performance(signal_date=signal, bars=bars)
        self.assertFalse(result["horizons"]["3M"]["complete"])
        self.assertEqual(20, result["horizons"]["3M"]["availableSessions"])
        self.assertIsNone(result["horizons"]["3M"]["returnPct"])
        self.assertEqual(Decimal("5.00"), result["performanceToDate"]["returnPct"])


if __name__ == "__main__": unittest.main()
