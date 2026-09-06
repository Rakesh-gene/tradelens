from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import PatternState, SwingType
from pattern_engine.models import DetectionContext, SwingPoint
from pattern_engine.pullback_detectors import detect_pullbacks


_D = Decimal
_ISIN = "INE000000001"


def _history(count=70):
    start = date(2024, 1, 1)
    bars, features = [], []
    for index in range(count):
        day = start + timedelta(days=index)
        bars.append({
            "isin": _ISIN, "trading_date": day, "open_price": _D("109"),
            "high_price": _D("112"), "low_price": _D("104"),
            "close_price": _D("110"), "volume": 100,
        })
        features.append({
            "isin": _ISIN, "trading_date": day, "atr_14": _D("2"),
            "natr_14": _D("2"), "ema_20": _D("105"), "sma_50": _D("100"),
            "sma_200": _D("90"), "ema_20_slope": _D("0.2"),
            "sma_50_slope": _D("0.1"), "median_volume_20": _D("100"),
            "close_location_value": _D("0.8"), "relative_strength_percentile": _D("80"),
        })
    return bars, features


def _context(bars):
    return DetectionContext(bars[-1]["trading_date"], {}, None, ("TREND-S2",), "v1")


def _swing(bars, index, price):
    return SwingPoint(
        f"H-{index}", _ISIN, bars[index]["trading_date"],
        bars[index + 3]["trading_date"], SwingType.HIGH, _D(price), _D("2"), _D("5"), True,
    )


class PullbackDetectorTestCase(unittest.TestCase):
    def setUp(self):
        self.configuration = load_pattern_engine_configuration()

    def _detect(self, bars, features, swings=(), sources=(), context=None):
        return detect_pullbacks(
            {"isin": _ISIN}, bars, features, swings, sources,
            context or _context(bars), self.configuration,
        )

    def test_breakout_retest_links_confirmed_persisted_source_and_triggers(self):
        bars, features = _history(15)
        breakout_index = 3
        bars[breakout_index].update(high_price=_D("102"), close_price=_D("101"))
        bars[6].update(high_price=_D("105"), close_price=_D("104"))
        bars[12].update(high_price=_D("102"), low_price=_D("101"), close_price=_D("101.5"), volume=70)
        bars[13].update(high_price=_D("101"), low_price=_D("100"), close_price=_D("100.5"), volume=60)
        bars[14].update(high_price=_D("104"), low_price=_D("101"), close_price=_D("103"), volume=80)
        source = {
            "pattern_instance_id": "breakout-1", "isin": _ISIN,
            "pattern_type": "BRK-RANGE", "state": PatternState.CONFIRMED,
            "pivot_price": _D("100"), "quality_score": _D("85"),
            "trigger_date": bars[breakout_index]["trading_date"],
        }

        candidate = next(item for item in self._detect(bars, features, sources=(source,)) if item.pattern_type == "PB-BRKRET")

        self.assertEqual(PatternState.TRIGGERED, candidate.state)
        self.assertEqual("breakout-1", candidate.measurements["source_pattern_instance_id"])
        self.assertEqual(_D("12"), candidate.measurements["maximum_advance_pct"])
        self.assertIn("breakout-1", candidate.supporting_pattern_identifiers)
        self.assertEqual(sum(candidate.measurements["quality_components"].values(), _D("0")), candidate.quality_score)

        ignored = dict(source, pattern_instance_id=None)
        self.assertNotIn("PB-BRKRET", {item.pattern_type for item in self._detect(bars, features, sources=(ignored,))})

    def test_breakout_retest_invalidates_after_two_closes_below_tolerance(self):
        bars, features = _history(15)
        bars[6].update(high_price=_D("105"))
        bars[13].update(low_price=_D("98"), close_price=_D("98"))
        bars[14].update(low_price=_D("97"), close_price=_D("98"))
        source = {
            "pattern_instance_id": "breakout-2", "isin": _ISIN,
            "pattern_type": "BRK-52WH", "state": "CONFIRMED",
            "pivot_price": _D("100"), "quality_score": _D("75"),
            "trigger_date": bars[3]["trading_date"],
        }

        candidate = next(item for item in self._detect(bars, features, sources=(source,)) if item.pattern_type == "PB-BRKRET")

        self.assertEqual(PatternState.INVALIDATED, candidate.state)
        self.assertEqual("two_closes_below_retest_zone", candidate.measurements["invalidation_reason"])

    def test_breakout_retest_ignores_touch_before_session_three(self):
        bars, features = _history(10)
        for index in range(2, 10):
            bars[index].update(
                open_price=_D("102"), high_price=_D("103"),
                low_price=_D("102"), close_price=_D("102"),
            )
        bars[2].update(high_price=_D("105"), low_price=_D("103"), close_price=_D("104"))
        bars[3].update(low_price=_D("100"), close_price=_D("101"))
        source = {
            "pattern_instance_id": "breakout-early", "isin": _ISIN,
            "pattern_type": "BRK-RANGE", "state": "CONFIRMED",
            "pivot_price": _D("100"), "quality_score": _D("80"),
            "trigger_date": bars[1]["trading_date"],
        }

        candidate = next(
            item for item in self._detect(bars, features, sources=(source,))
            if item.pattern_type == "PB-BRKRET"
        )

        self.assertEqual(PatternState.FORMING, candidate.state)
        self.assertIsNone(candidate.measurements["retest_touch_date"])
        self.assertIsNone(candidate.measurements["retest_session_after_breakout"])

    def test_breakout_retest_advance_uses_breakout_date_atr(self):
        bars, features = _history(10)
        for index in range(2, 10):
            bars[index].update(
                open_price=_D("102"), high_price=_D("103"),
                low_price=_D("102"), close_price=_D("102"),
            )
        bars[2].update(high_price=_D("105"), low_price=_D("103"), close_price=_D("104"))
        bars[5].update(low_price=_D("100"), close_price=_D("101"))
        features[1]["atr_14"] = _D("6")
        source = {
            "pattern_instance_id": "breakout-atr", "isin": _ISIN,
            "pattern_type": "BRK-RANGE", "state": "CONFIRMED",
            "pivot_price": _D("100"), "quality_score": _D("80"),
            "trigger_date": bars[1]["trading_date"],
        }

        self.assertNotIn(
            "PB-BRKRET",
            {item.pattern_type for item in self._detect(bars, features, sources=(source,))},
        )

    def test_ema20_pullback_triggers_after_touch_and_two_session_high(self):
        bars, features = _history()
        high_index = 65
        bars[high_index].update(high_price=_D("120"), close_price=_D("118"))
        bars[66].update(high_price=_D("116"), low_price=_D("113"), close_price=_D("114"))
        bars[67].update(high_price=_D("112"), low_price=_D("109"), close_price=_D("110"))
        bars[68].update(high_price=_D("108"), low_price=_D("106"), close_price=_D("107"), volume=60)
        bars[69].update(high_price=_D("114"), low_price=_D("108"), close_price=_D("113"), volume=80)

        candidates = self._detect(bars, features, (_swing(bars, high_index, "120"),))
        candidate = next(item for item in candidates if item.pattern_type == "PB-EMA20")

        self.assertEqual(PatternState.TRIGGERED, candidate.state)
        self.assertEqual(bars[68]["trading_date"], candidate.measurements["touch_date"])
        self.assertGreaterEqual(candidate.measurements["prior_closes_above_ma"], 10)
        self.assertIn("TREND-S2", candidate.supporting_pattern_identifiers)
        self.assertEqual(_D("105"), candidate.measurements["trend_prerequisites"]["ema_20"])
        self.assertEqual(_D("100"), candidate.measurements["trend_prerequisites"]["sma_50"])

    def test_ema20_can_invalidate_while_sma50_candidate_remains_ready(self):
        bars, features = _history()
        high_index = 65
        bars[high_index].update(high_price=_D("110"), close_price=_D("109"))
        bars[66].update(high_price=_D("114"), low_price=_D("110"), close_price=_D("112"))
        bars[67].update(high_price=_D("110"), low_price=_D("106"), close_price=_D("108"))
        bars[68].update(high_price=_D("106"), low_price=_D("104.5"), close_price=_D("102"))
        bars[69].update(high_price=_D("103"), low_price=_D("100"), close_price=_D("102"))
        features[69]["close_location_value"] = _D("0.67")

        candidates = self._detect(bars, features, (_swing(bars, high_index, "110"),))
        by_type = {candidate.pattern_type: candidate for candidate in candidates}

        self.assertEqual(PatternState.INVALIDATED, by_type["PB-EMA20"].state)
        self.assertEqual(PatternState.READY, by_type["PB-SMA50"].state)
        self.assertEqual("PB-SMA50-T1", by_type["PB-SMA50"].variant)

    def test_sma50_distinct_touch_episodes_derive_t3_plus_variant(self):
        bars, features = _history(80)
        for index in (20, 40):
            bars[index].update(low_price=_D("100"), close_price=_D("104"))
        high_index = 74
        bars[high_index].update(high_price=_D("110"), close_price=_D("108"))
        bars[75].update(low_price=_D("104"), high_price=_D("108"), close_price=_D("106"))
        bars[76].update(low_price=_D("102"), high_price=_D("106"), close_price=_D("104"))
        bars[77].update(low_price=_D("100"), high_price=_D("104"), close_price=_D("102"), volume=60)
        bars[78].update(low_price=_D("102"), high_price=_D("105"), close_price=_D("104"))
        bars[79].update(low_price=_D("103"), high_price=_D("110"), close_price=_D("108"))

        candidate = next(
            item for item in self._detect(bars, features, (_swing(bars, high_index, "110"),))
            if item.pattern_type == "PB-SMA50"
        )

        self.assertEqual("PB-SMA50-T3+", candidate.variant)
        self.assertEqual(3, candidate.measurements["touch_episode_count"])
        self.assertEqual(PatternState.TRIGGERED, candidate.state)

    def test_future_rows_and_unconfirmed_swings_are_not_consumed(self):
        bars, features = _history()
        high_index = 65
        bars[high_index].update(high_price=_D("120"))
        bars[68].update(low_price=_D("105"))
        replay_context = DetectionContext(bars[68]["trading_date"], {}, None, (), "v1")
        future_confirmed = SwingPoint(
            "future", _ISIN, bars[65]["trading_date"], bars[69]["trading_date"],
            SwingType.HIGH, _D("120"), _D("2"), _D("5"), True,
        )

        future_source = {
            "pattern_instance_id": "future-source", "isin": _ISIN,
            "pattern_type": "BRK-RANGE", "state": "CONFIRMED",
            "pivot_price": _D("100"), "quality_score": _D("80"),
            "trigger_date": bars[65]["trading_date"],
            "confirmation_date": bars[69]["trading_date"],
        }

        self.assertEqual(
            [],
            self._detect(
                bars, features, (future_confirmed,), (future_source,), context=replay_context
            ),
        )


if __name__ == "__main__":
    unittest.main()
