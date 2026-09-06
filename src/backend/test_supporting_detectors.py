from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import SwingType
from pattern_engine.models import DetectionContext, SwingPoint
from pattern_engine.supporting_detectors import detect_supporting_patterns


def _snapshot(days: int = 252):
    start = date(2025, 1, 1)
    bars = []
    features = []
    for index in range(days):
        day = start + timedelta(days=index)
        close = Decimal("100") if index < days - 22 else Decimal("300")
        high, low = close + 1, close - 1
        if index == days - 2: high, low = Decimal("302"), Decimal("298")
        if index == days - 1: high, low = Decimal("300.5"), Decimal("299.5")
        bars.append({"isin": "INE000000001", "trading_date": day, "open_price": close, "high_price": high, "low_price": low, "close_price": close, "volume": 150})
        features.append({
            "isin": "INE000000001", "trading_date": day, "range_5": Decimal("1"), "range_10": Decimal("2"), "range_20": Decimal("4"), "range_50": Decimal("5"),
            "atr_5": Decimal("1"), "atr_10": Decimal("1"), "atr_14": Decimal("1"), "atr_20": Decimal("2"), "atr_50": Decimal("2"),
            "median_volume_5": Decimal("50"), "median_volume_20": Decimal("100"), "median_volume_50": Decimal("100"),
            "ema_20": Decimal("250"), "sma_50": Decimal("200"), "sma_100": Decimal("175"), "sma_200": Decimal("150"),
            "secondary_metrics": {f"rs_{h}_percentile": Decimal("80") for h in ("1m", "3m", "6m", "12m")},
            "ema_20_slope": Decimal("1"), "sma_50_slope": Decimal("1"), "sma_200_slope": Decimal("1"),
            "range_position_52_week": Decimal("90"), "relative_strength_percentile": Decimal("80"), "relative_strength_composite": Decimal("10"),
            "return_1_month": Decimal("12"), "return_3_month": Decimal("30"), "return_6_month": Decimal("48"), "return_12_month": Decimal("72"),
        })
    as_of = bars[-1]["trading_date"]
    swings = [
        SwingPoint("l1", "INE000000001", start + timedelta(days=10), start + timedelta(days=13), SwingType.LOW, Decimal("100"), Decimal("1"), None, True),
        SwingPoint("h1", "INE000000001", start + timedelta(days=20), start + timedelta(days=23), SwingType.HIGH, Decimal("110"), Decimal("1"), None, True),
        SwingPoint("l2", "INE000000001", start + timedelta(days=30), start + timedelta(days=33), SwingType.LOW, Decimal("105"), Decimal("1"), None, True),
        SwingPoint("h2", "INE000000001", start + timedelta(days=40), start + timedelta(days=43), SwingType.HIGH, Decimal("115"), Decimal("1"), None, True),
        SwingPoint("l3", "INE000000001", start + timedelta(days=50), start + timedelta(days=53), SwingType.LOW, Decimal("110"), Decimal("1"), None, True),
        SwingPoint("h3", "INE000000001", start + timedelta(days=60), start + timedelta(days=63), SwingType.HIGH, Decimal("120"), Decimal("1"), None, True),
    ]
    context = DetectionContext(as_of, {"bars": tuple({"trading_date": b["trading_date"], "close_price": b["close_price"] / Decimal(i + 1)} for i, b in enumerate(bars))}, None, (), "v1")
    return bars, features, swings, context


class SupportingDetectorTestCase(unittest.TestCase):
    def setUp(self):
        self.configuration = load_pattern_engine_configuration()
        self.bars, self.features, self.swings, self.context = _snapshot()

    def test_all_supporting_identifiers_emit_auditable_candidates_from_true_fixture(self):
        candidates = detect_supporting_patterns({"isin": "INE000000001"}, self.bars, self.features, self.swings, (), self.context, self.configuration)
        by_type = {candidate.pattern_type: candidate for candidate in candidates}

        self.assertEqual(set(by_type), {"BASE-TIGHT", "TREND-HHHL", "TREND-S2", "TREND-MA", "COMP-NR7", "COMP-IB", "COMP-ATR", "COMP-RANGE", "MOM-ACC", "MOM-RSL", "MOM-RSB", "VOL-DRY", "VOL-EXP"})
        for candidate in by_type.values():
            self.assertEqual(candidate.detected_date, self.context.as_of_date)
            self.assertEqual(candidate.measurements["as_of_date"], self.context.as_of_date)
        self.assertEqual(by_type["COMP-IB"].variant, "COMP-IB1")
        self.assertEqual(by_type["COMP-NR7"].measurements["daily_range_pct"], Decimal("1") / 300 * 100)
        self.assertEqual(by_type["VOL-EXP"].measurements["strength_band"], "STRONG")

    def test_false_fixture_suppresses_threshold_dependent_candidates(self):
        self.features[-1]["relative_strength_percentile"] = Decimal("69.99")
        self.features[-1]["secondary_metrics"] = {f"rs_{h}_percentile": Decimal("69.99") for h in ("1m", "3m", "6m", "12m")}
        self.features[-1]["atr_5"] = Decimal("2")
        self.features[-1]["median_volume_5"] = Decimal("71")
        self.bars[-1]["volume"] = 119
        candidates = detect_supporting_patterns({"isin": "INE000000001"}, self.bars, self.features, self.swings, (), self.context, self.configuration)
        identifiers = {candidate.pattern_type for candidate in candidates}

        self.assertNotIn("MOM-RSL", identifiers)
        self.assertNotIn("COMP-ATR", identifiers)
        self.assertNotIn("VOL-DRY", identifiers)
        self.assertNotIn("VOL-EXP", identifiers)

    def test_insufficient_and_boundary_fixtures_are_safe_and_inclusive(self):
        self.assertEqual(detect_supporting_patterns({"isin": "INE000000001"}, self.bars[:6], self.features[:6], (), (), self.context, self.configuration), [])
        self.features[-1]["relative_strength_percentile"] = Decimal("70")
        self.features[-1]["secondary_metrics"] = {f"rs_{h}_percentile": Decimal("70") for h in ("1m", "3m", "6m", "12m")}
        candidates = detect_supporting_patterns({"isin": "INE000000001"}, self.bars, self.features, self.swings, (), self.context, self.configuration)
        self.assertIn("MOM-RSL", {candidate.pattern_type for candidate in candidates})


if __name__ == "__main__":
    unittest.main()
