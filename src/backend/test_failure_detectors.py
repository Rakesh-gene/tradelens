from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import PatternClass, PatternState, SwingType
from pattern_engine.failure_detectors import detect_failures
from pattern_engine.models import DetectionContext, SwingPoint


_D = Decimal
_ISIN = "INE000000001"


def _history(count=70):
    start = date(2024, 1, 1)
    bars, features = [], []
    for index in range(count):
        day = start + timedelta(days=index)
        bars.append({
            "isin": _ISIN, "trading_date": day, "open_price": _D("109"),
            "high_price": _D("112"), "low_price": _D("108"),
            "close_price": _D("110"), "volume": 100,
        })
        features.append({
            "isin": _ISIN, "trading_date": day, "atr_14": _D("2"),
            "ema_20": _D("105"), "sma_50": _D("100"), "sma_200": _D("90"),
            "ema_20_slope": _D("0.2"), "sma_50_slope": _D("0.1"),
            "median_volume_20": _D("100"), "relative_strength_percentile": _D("80"),
        })
    return bars, features


def _context(bars):
    return DetectionContext(bars[-1]["trading_date"], {}, None, (), "v1")


def _source(bars, pattern_type, instance_id, **values):
    result = {
        "pattern_instance_id": instance_id,
        "isin": _ISIN,
        "pattern_type": pattern_type,
        "variant": values.pop("variant", None),
        "state": values.pop("state", PatternState.CONFIRMED),
        "start_date": values.pop("start_date", bars[-10]["trading_date"]),
        "detected_date": values.pop("detected_date", bars[-5]["trading_date"]),
        "quality_score": values.pop("quality_score", _D("82")),
        "measurements": values.pop("measurements", {}),
    }
    result.update(values)
    return result


class FailureDetectorTestCase(unittest.TestCase):
    def setUp(self):
        self.configuration = load_pattern_engine_configuration()

    def _detect(self, bars, features, swings=(), sources=(), context=None):
        return detect_failures(
            {"isin": _ISIN}, bars, features, swings, sources,
            context or _context(bars), self.configuration,
        )

    def test_failed_breakout_records_complete_source_linked_evidence(self):
        bars, features = _history()
        breakout_date = bars[-5]["trading_date"]
        bars[-5].update(high_price=_D("103"), low_price=_D("99"), close_price=_D("101"))
        features[-5]["relative_strength_percentile"] = _D("90")
        bars[-4].update(high_price=_D("106"), close_price=_D("104"))
        bars[-3].update(high_price=_D("104"), close_price=_D("100"))
        bars[-2].update(high_price=_D("103"), close_price=_D("101"))
        bars[-1].update(high_price=_D("100"), low_price=_D("97"), close_price=_D("98"), volume=150)
        features[-1]["relative_strength_percentile"] = _D("60")
        source = _source(
            bars, "BRK-RANGE", "breakout-1", pivot_price=_D("100"),
            detected_date=breakout_date, measurements={"breakout_date": breakout_date},
        )

        candidate = next(item for item in self._detect(bars, features, sources=(source,)) if item.pattern_type == "FAIL-BRK")

        self.assertEqual(PatternClass.FAILURE, candidate.pattern_class)
        self.assertEqual(PatternState.DETECTED, candidate.state)
        self.assertEqual("breakout-1", candidate.measurements["source_pattern_instance_id"])
        self.assertEqual(_D("106"), candidate.measurements["highest_advance_after_breakout"])
        self.assertEqual(_D("6"), candidate.measurements["maximum_advance_amount"])
        self.assertEqual(_D("3"), candidate.measurements["maximum_advance_atr"])
        self.assertEqual(3, candidate.measurements["days_above_pivot"])
        self.assertEqual(_D("30"), candidate.measurements["rs_deterioration"])
        self.assertTrue(candidate.measurements["close_below_breakout_candle"])
        self.assertTrue(candidate.measurements["strong_failure"])

    def test_breakout_and_base_threshold_equality_do_not_emit(self):
        bars, features = _history()
        bars[-1].update(close_price=_D("99.5"), low_price=_D("99"))
        breakout = _source(
            bars, "BRK-52WH", "breakout-equality", pivot_price=_D("100"),
            measurements={"breakout_date": bars[-5]["trading_date"]},
        )
        base = _source(
            bars, "BASE-FLAT", "base-equality", support_price=_D("99.5"),
            measurements={"support_tolerance_pct": _D("0")},
        )

        types = {item.pattern_type for item in self._detect(bars, features, sources=(breakout, base))}

        self.assertNotIn("FAIL-BRK", types)
        self.assertNotIn("FAIL-BASE", types)

    def test_failed_base_records_support_volume_trend_and_sma_distance(self):
        bars, features = _history()
        bars[-1].update(close_price=_D("97"), low_price=_D("96"), volume=140)
        source = _source(
            bars, "BASE-VCP", "base-1", variant="VCP-3C",
            pivot_price=_D("115"), support_price=_D("100"),
        )

        candidate = next(item for item in self._detect(bars, features, sources=(source,)) if item.pattern_type == "FAIL-BASE")

        self.assertEqual("base-1", candidate.measurements["source_pattern_instance_id"])
        self.assertEqual(_D("3"), candidate.measurements["support_penetration_pct"])
        self.assertEqual(_D("1.4"), candidate.measurements["volume_ratio_20"])
        self.assertGreater(candidate.measurements["distance_below_sma50_pct"], 0)
        self.assertIsNotNone(candidate.measurements["trend_score"])

    def test_failed_base_prefers_source_invalidation_over_generic_tolerance(self):
        bars, features = _history()
        bars[-1].update(close_price=_D("98.5"), low_price=_D("98"))
        source = _source(
            bars, "BASE-FLAT", "base-invalidation", support_price=_D("100"),
            invalidation_price=_D("99"),
        )

        candidate = next(
            item for item in self._detect(bars, features, sources=(source,))
            if item.pattern_type == "FAIL-BASE"
        )

        self.assertEqual(_D("99"), candidate.measurements["support_failure_threshold"])
        self.assertEqual(_D("1"), candidate.measurements["support_tolerance_pct"])

    def test_ema20_requires_two_closes_and_more_than_one_atr_or_swing_break(self):
        bars, features = _history()
        bars[-2].update(close_price=_D("103"), low_price=_D("102"))
        bars[-1].update(close_price=_D("103"), low_price=_D("102"), volume=120)
        source = _source(bars, "PB-EMA20", "ema-1")

        self.assertNotIn(
            "FAIL-EMA20",
            {item.pattern_type for item in self._detect(bars, features, sources=(source,))},
        )

        bars[-1].update(close_price=_D("102.5"))
        candidate = next(
            item for item in self._detect(bars, features, sources=(source,))
            if item.pattern_type == "FAIL-EMA20"
        )
        self.assertEqual(2, candidate.measurements["days_below_ema20"])
        self.assertEqual(_D("1.25"), candidate.measurements["maximum_penetration_atr"])
        self.assertEqual(_D("82"), candidate.measurements["previous_trend_quality"])

    def test_ema20_swing_break_can_trigger_without_one_atr_penetration(self):
        bars, features = _history()
        bars[-2].update(close_price=_D("104.5"), low_price=_D("104"))
        bars[-1].update(close_price=_D("104"), low_price=_D("103.5"))
        swing = SwingPoint(
            "low-1", _ISIN, bars[-6]["trading_date"], bars[-3]["trading_date"],
            SwingType.LOW, _D("104.25"), _D("2"), _D("4"), True,
        )

        candidate = next(
            item for item in self._detect(bars, features, (swing,))
            if item.pattern_type == "FAIL-EMA20"
        )

        self.assertTrue(candidate.measurements["swing_low_broken"])
        self.assertLess(candidate.measurements["maximum_penetration_atr"], _D("1"))

    def test_sma50_accepts_one_atr_boundary_and_marks_nonpositive_slope_stronger(self):
        bars, features = _history()
        bars[-2].update(close_price=_D("99"), low_price=_D("98"))
        bars[-1].update(close_price=_D("98"), low_price=_D("97"), volume=160)
        features[-1]["sma_50_slope"] = _D("0")
        source = _source(bars, "PB-SMA50", "sma-1", variant="PB-SMA50-T2")

        candidate = next(
            item for item in self._detect(bars, features, sources=(source,))
            if item.pattern_type == "FAIL-SMA50"
        )

        self.assertEqual(_D("1"), candidate.measurements["break_atr"])
        self.assertEqual(2, candidate.measurements["days_below"])
        self.assertTrue(candidate.measurements["stronger_failure"])
        self.assertEqual("sma-1", candidate.measurements["source_pattern_instance_id"])

    def test_structural_failure_uses_latest_visible_meaningful_low_and_trend_source(self):
        bars, features = _history()
        old = SwingPoint(
            "old", _ISIN, bars[-20]["trading_date"], bars[-17]["trading_date"],
            SwingType.LOW, _D("95"), _D("2"), _D("4"), True,
        )
        latest = SwingPoint(
            "latest", _ISIN, bars[-8]["trading_date"], bars[-5]["trading_date"],
            SwingType.LOW, _D("105"), _D("2"), _D("4"), True,
        )
        features[-8]["relative_strength_percentile"] = _D("90")
        features[-1]["relative_strength_percentile"] = _D("70")
        bars[-1].update(close_price=_D("104"), low_price=_D("103"), volume=130)
        trend = _source(bars, "TREND-HHHL", "trend-1", start_date=bars[-30]["trading_date"])

        candidate = next(
            item for item in self._detect(bars, features, (old, latest), (trend,))
            if item.pattern_type == "FAIL-STRUCT"
        )

        self.assertEqual("latest", candidate.measurements["broken_swing_id"])
        self.assertEqual(_D("20"), candidate.measurements["rs_deterioration"])
        self.assertEqual("trend-1", candidate.measurements["source_pattern_instance_id"])
        self.assertEqual(29, candidate.measurements["trend_age_sessions"])

    def test_future_sources_swings_bars_and_features_are_ignored(self):
        bars, features = _history()
        replay_context = DetectionContext(bars[-2]["trading_date"], {}, None, (), "v1")
        future_swing = SwingPoint(
            "future", _ISIN, bars[-5]["trading_date"], bars[-1]["trading_date"],
            SwingType.LOW, _D("200"), _D("2"), _D("4"), True,
        )
        future_source = _source(
            bars, "BASE-FLAT", "future-base", support_price=_D("200"),
            last_updated_date=bars[-1]["trading_date"],
        )

        self.assertEqual(
            [],
            self._detect(
                bars, features, (future_swing,), (future_source,), context=replay_context
            ),
        )


if __name__ == "__main__":
    unittest.main()
