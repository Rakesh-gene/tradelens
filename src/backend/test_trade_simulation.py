from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.trade_simulation import SwingTradePolicy, simulate_swing_trade


def bar(day, opening, high, low, close):
    return {"trading_date": day, "open_price": Decimal(opening), "high_price": Decimal(high), "low_price": Decimal(low), "close_price": Decimal(close)}


class SwingTradeSimulationTest(unittest.TestCase):
    def test_enters_next_session_and_hits_target(self):
        signal = date(2026, 1, 1)
        result = simulate_swing_trade(signal_date=signal, invalidation_price="95", pivot_price="100", bars=[bar(signal + timedelta(days=1), "100", "101", "99", "100"), bar(signal + timedelta(days=2), "110", "111", "105", "110")])
        self.assertEqual(signal + timedelta(days=1), result["entry_date"])
        self.assertEqual("TARGET_HIT", result["exit_reason"])
        self.assertEqual(200, result["quantity"])
        self.assertEqual(Decimal("2000"), result["gross_pnl"])

    def test_same_candle_stop_and_target_is_stop_first(self):
        signal = date(2026, 1, 1)
        result = simulate_swing_trade(signal_date=signal, invalidation_price="95", bars=[bar(signal + timedelta(days=1), "100", "100", "99", "100"), bar(signal + timedelta(days=2), "100", "111", "94", "100")])
        self.assertEqual("AMBIGUOUS_INTRADAY_SEQUENCE", result["exit_reason"])
        self.assertTrue(result["ambiguous"])
        self.assertEqual(Decimal("95"), result["exit_price"])

    def test_gap_and_missing_invalidation_are_explicit(self):
        signal = date(2026, 1, 1)
        rows = [bar(signal + timedelta(days=1), "110", "110", "109", "110")]
        self.assertEqual("ENTRY_GAP_TOO_LARGE", simulate_swing_trade(signal_date=signal, invalidation_price="95", pivot_price="100", bars=rows)["exit_reason"])
        self.assertEqual("MISSING_INVALIDATION", simulate_swing_trade(signal_date=signal, invalidation_price=None, bars=rows)["exit_reason"])

    def test_entry_day_stop_is_not_ignored(self):
        signal = date(2026, 1, 1)
        result = simulate_swing_trade(signal_date=signal, invalidation_price="95", bars=[bar(signal + timedelta(days=1), "100", "101", "94", "96")])
        self.assertEqual("STOP_LOSS", result["exit_reason"])
        self.assertEqual(0, result["duration_sessions"])

    def test_bearish_target_costs_and_excursions_are_direction_aware(self):
        signal = date(2026, 1, 1)
        policy = SwingTradePolicy(round_trip_cost_pct=Decimal("0.1"), fixed_cost=Decimal("10"))
        result = simulate_swing_trade(signal_date=signal, direction="BEARISH", invalidation_price="105", pivot_price="100", policy=policy, bars=[bar(signal + timedelta(days=1), "100", "101", "89", "90")])
        self.assertEqual("TARGET_HIT", result["exit_reason"])
        self.assertEqual(Decimal("2000"), result["gross_pnl"])
        self.assertEqual(Decimal("30.0"), result["costs"])
        self.assertGreater(result["mfe_pct"], 0)

    def test_time_exit_and_incomplete_history_are_distinct(self):
        signal = date(2026, 1, 1)
        rows = [bar(signal + timedelta(days=index), "100", "104", "96", "101") for index in range(1, 21)]
        complete = simulate_swing_trade(signal_date=signal, invalidation_price="95", bars=rows)
        incomplete = simulate_swing_trade(signal_date=signal, invalidation_price="95", bars=rows[:19])
        self.assertEqual("TIME_EXIT", complete["exit_reason"])
        self.assertEqual("INSUFFICIENT_FUTURE_HISTORY", incomplete["exit_reason"])
