from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.features import FeatureService, assign_relative_strength_percentiles, compute_features


def _bars(count: int, *, flat: bool = False):
    start = date(2020, 1, 1)
    return [{
        "isin": "INE000000001", "trading_date": start + timedelta(days=index),
        "open_price": Decimal("100") + index, "high_price": Decimal("102") + index,
        "low_price": Decimal("99") + index, "close_price": Decimal("101") + index,
        "volume": 1000 + index, "delivery_percentage": Decimal("50"),
    } for index in range(count)] if not flat else [{
        "isin": "INE000000001", "trading_date": start, "open_price": Decimal("100"),
        "high_price": Decimal("100"), "low_price": Decimal("100"), "close_price": Decimal("100"), "volume": 1000,
    }]


class FeatureRepository:
    def __init__(self, bars): self.bars, self.saved = bars, []
    def load_adjusted_bars(self, *_args): return self.bars
    def upsert_technical_features(self, features): self.saved = list(features); return len(features)


class FeatureEngineTestCase(unittest.TestCase):
    def test_true_range_wilder_atr_ema_and_median_volume_have_expected_seed_behavior(self):
        features = compute_features(_bars(21), "feature-v1", "adjusted-v1")

        self.assertEqual(features[0]["true_range"], Decimal("3"))
        self.assertIsNone(features[3]["atr_5"])
        self.assertEqual(features[4]["atr_5"], Decimal("3"))
        self.assertEqual(features[9]["ema_10"], Decimal("105.5"))
        self.assertEqual(features[9]["median_volume_5"], Decimal("1007"))
        self.assertEqual(features[9]["close_location_value"], Decimal(2) / Decimal(3))
        self.assertEqual(features[4]["range_5"], Decimal("7") / Decimal("106") * 100)
        self.assertEqual(features[19]["volume_ratio_20"], Decimal("1019") / Decimal("1009.5"))
        self.assertEqual(features[19]["median_traded_value_20"], Decimal("111550"))

    def test_zero_range_clv_and_insufficient_history_are_safe(self):
        feature = compute_features(_bars(1, flat=True), "feature-v1", "adjusted-v1")[0]

        self.assertEqual(feature["close_location_value"], Decimal("0.5"))
        self.assertIsNone(feature["atr_14"])
        self.assertIsNone(feature.get("high_52_week"))

    def test_52_week_reference_excludes_candidate_bar_and_aligns_benchmark_by_date(self):
        bars = _bars(253)
        bars[-1]["high_price"] = Decimal("1000")
        benchmark = [{"trading_date": item["trading_date"], "close_price": Decimal("101") + index} for index, item in enumerate(bars)]
        feature = compute_features(bars, "feature-v1", "adjusted-v1", benchmark)[-1]

        self.assertEqual(feature["high_52_week"], Decimal("353"))
        self.assertEqual(feature["distance_to_52_week_high_pct"], Decimal("0"))
        self.assertEqual(feature["relative_strength_12m"], Decimal("0"))

    def test_long_golden_series_populates_shared_detector_measurements(self):
        bars = _bars(253)
        benchmark = [{"trading_date": row["trading_date"], "close_price": row["close_price"]} for row in bars]
        feature = compute_features(bars, "feature-v1", "adjusted-v1", benchmark)[-1]

        self.assertEqual([feature[f"atr_{period}"] for period in (5, 10, 14, 20, 50)], [Decimal("3")] * 5)
        self.assertEqual(feature["ema_20"], Decimal("343.5"))
        self.assertEqual(feature["sma_50"], Decimal("328.5"))
        self.assertEqual(feature["range_50"], Decimal("52") / Decimal("354") * 100)
        self.assertEqual(feature["median_volume_50"], Decimal("1227.5"))
        self.assertEqual(feature["distance_to_sma_50_pct"], (Decimal("353") - Decimal("328.5")) / Decimal("328.5") * 100)
        self.assertEqual(feature["return_1_month"], Decimal("21") / Decimal("332") * 100)
        self.assertEqual(feature["relative_strength_composite"], Decimal("0"))

    def test_unequal_benchmark_calendar_returns_unavailable_instead_of_array_alignment(self):
        bars = _bars(22)
        benchmark = [{"trading_date": row["trading_date"], "close_price": row["close_price"]} for row in bars]
        benchmark.pop(0)

        feature = compute_features(bars, "feature-v1", "adjusted-v1", benchmark)[-1]

        self.assertIsNone(feature["relative_strength_1m"])

    def test_flat_52_week_window_avoids_zero_denominator(self):
        start = date(2020, 1, 1)
        bars = [{
            "isin": "INE000000001", "trading_date": start + timedelta(days=index),
            "open_price": Decimal("100"), "high_price": Decimal("100"),
            "low_price": Decimal("100"), "close_price": Decimal("100"), "volume": 1000,
        } for index in range(253)]

        feature = compute_features(bars, "feature-v1", "adjusted-v1")[-1]

        self.assertIsNone(feature["range_position_52_week"])

    def test_incremental_rebuild_writes_only_required_suffix_with_full_calculation_context(self):
        repository = FeatureRepository(_bars(30))
        service = FeatureService(repository)

        written = service.rebuild("INE000000001", date(2020, 1, 1), date(2020, 2, 1), "adjusted-v1", "feature-v1", changed_from_date=date(2020, 1, 21))

        self.assertEqual(written, 30)  # 1,260-session lookback safely reaches the available first bar
        self.assertEqual(repository.saved[-1]["trading_date"], date(2020, 1, 30))

    def test_cross_sectional_percentile_ties_share_a_rank(self):
        rows = [{"relative_strength_composite": Decimal("10")}, {"relative_strength_composite": Decimal("10")}, {"relative_strength_composite": Decimal("20")}]
        assign_relative_strength_percentiles(rows)

        self.assertEqual([row["relative_strength_percentile"] for row in rows], [Decimal("0"), Decimal("0"), Decimal("100")])

    def test_cross_sectional_percentiles_exclude_ineligible_securities(self):
        rows = [
            {"isin": "A", "relative_strength_composite": Decimal("10")},
            {"isin": "B", "relative_strength_composite": Decimal("100")},
            {"isin": "C", "relative_strength_composite": Decimal("20")},
        ]
        assign_relative_strength_percentiles(rows, {"A", "C"})

        self.assertEqual(rows[0]["relative_strength_percentile"], Decimal("0"))
        self.assertNotIn("relative_strength_percentile", rows[1])
        self.assertEqual(rows[2]["relative_strength_percentile"], Decimal("100"))

    def test_delivery_expansion_uses_five_session_median_over_twenty_session_median(self):
        bars = _bars(20)
        for index, bar in enumerate(bars):
            bar["delivery_percentage"] = Decimal("80") if index >= 15 else Decimal("40")
            bar["deliverable_quantity"] = 500 + index

        feature = compute_features(bars, "feature-v1", "adjusted-v1")[-1]

        self.assertEqual(feature["median_delivery_percentage_5"], Decimal("80"))
        self.assertEqual(feature["median_delivery_percentage_20"], Decimal("40"))
        self.assertEqual(feature["delivery_expansion_ratio"], Decimal("2"))
        self.assertEqual(feature["deliverable_volume"], Decimal("519"))

    def test_incremental_output_matches_full_recomputation_for_same_dates(self):
        bars = _bars(1300)
        repository = FeatureRepository(bars)
        service = FeatureService(repository)
        changed = bars[-10]["trading_date"]

        service.rebuild("INE000000001", bars[0]["trading_date"], bars[-1]["trading_date"], "adjusted-v1", "feature-v1", changed_from_date=changed)
        full = compute_features(bars, "feature-v1", "adjusted-v1")
        expected = {row["trading_date"]: row for row in full}

        self.assertTrue(repository.saved)
        self.assertTrue(all(row == expected[row["trading_date"]] for row in repository.saved))


if __name__ == "__main__":
    unittest.main()
