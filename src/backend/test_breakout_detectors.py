from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.breakout_detectors import detect_breakouts
from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import PatternState, ZoneType
from pattern_engine.models import DetectionContext, PriceZone


_D = Decimal


def _snapshot(count: int = 25):
    start = date(2023, 1, 1)
    bars, features = [], []
    for index in range(count):
        day = start + timedelta(days=index)
        bars.append({"isin": "INE000000001", "trading_date": day, "open_price": _D("95"), "high_price": _D("100"), "low_price": _D("94"), "close_price": _D("95"), "volume": 100})
        features.append({"isin": "INE000000001", "trading_date": day, "atr_14": _D("1"), "median_volume_20": _D("100"), "close_location_value": _D("0.9"), "relative_strength_percentile": _D("80")})
    zone = PriceZone("r", "INE000000001", ZoneType.RESISTANCE, bars[1]["trading_date"], bars[3]["trading_date"], _D("100"), _D("1"), _D("0.5"), ("a", "b"), 2, _D("0.5"), bars[3]["trading_date"], bars[3]["trading_date"])
    return bars, features, zone


def _context(bars): return DetectionContext(bars[-1]["trading_date"], {}, None, (), "v1")


class BreakoutDetectorTestCase(unittest.TestCase):
    def setUp(self): self.configuration = load_pattern_engine_configuration()

    def _detect(self, bars, features, zones=()):
        return detect_breakouts({"isin": "INE000000001"}, bars, features, zones, _context(bars), self.configuration)

    def test_range_breakout_trigger_confirm_extend_and_fail_share_one_core(self):
        bars, features, zone = _snapshot()
        bars[-1].update(open_price=_D("100"), high_price=_D("102"), low_price=_D("99"), close_price=_D("101"), volume=150)
        triggered = next(candidate for candidate in self._detect(bars, features, (zone,)) if candidate.pattern_type == "BRK-RANGE")
        self.assertEqual(triggered.state, PatternState.TRIGGERED)
        self.assertEqual(triggered.measurements["breakout_magnitude_atr"], _D("1"))
        self.assertFalse(triggered.measurements["extended"])
        self.assertIn("volume_expansion", triggered.measurements["quality_components"])

        day = bars[-1]["trading_date"] + timedelta(days=1)
        bars.append({**bars[-1], "trading_date": day, "close_price": _D("101"), "high_price": _D("102")})
        features.append({**features[-1], "trading_date": day})
        confirmed = next(candidate for candidate in self._detect(bars, features, (zone,)) if candidate.pattern_type == "BRK-RANGE")
        self.assertEqual(confirmed.state, PatternState.CONFIRMED)

        bars[-1].update(close_price=_D("103"), high_price=_D("104"))
        extended = next(candidate for candidate in self._detect(bars, features, (zone,)) if candidate.pattern_type == "BRK-RANGE")
        self.assertTrue(extended.measurements["extended"])

        day = bars[-1]["trading_date"] + timedelta(days=1)
        bars.append({**bars[-1], "trading_date": day, "close_price": _D("98"), "low_price": _D("97"), "volume": 150})
        features.append({**features[-1], "trading_date": day})
        failed = self._detect(bars, features, (zone,))
        by_type = {candidate.pattern_type: candidate for candidate in failed}
        self.assertEqual(by_type["BRK-RANGE"].state, PatternState.FAILED)
        self.assertEqual(by_type["FAIL-BRK"].variant, "BRK-RANGE")
        self.assertTrue(by_type["FAIL-BRK"].measurements["strong_failure"])

    def test_no_candidate_at_buffer_equality_and_future_data_is_ignored(self):
        bars, features, zone = _snapshot()
        bars[-1].update(close_price=_D("100.5"), high_price=_D("101"))
        self.assertEqual(self._detect(bars, features, (zone,)), [])
        expected = self._detect(bars, features, (zone,))
        bars.append({**bars[-1], "trading_date": bars[-1]["trading_date"] + timedelta(days=1), "close_price": _D("200")})
        features.append({**features[-1], "trading_date": features[-1]["trading_date"] + timedelta(days=1)})
        self.assertEqual(expected, detect_breakouts({"isin": "INE000000001"}, bars, features, (zone,), _context(bars[:-1]), self.configuration))

    def test_prior_high_sources_exclude_current_bar_and_multi_year_variants_are_metadata_only(self):
        bars, features, _ = _snapshot(1261)
        for index, bar in enumerate(bars[:-1]):
            bar.update(high_price=_D("100") + _D(index % 7), low_price=_D("94"), close_price=_D("95"))
        bars[-1].update(open_price=_D("107"), high_price=_D("110"), low_price=_D("106"), close_price=_D("108"), volume=200)
        candidates = self._detect(bars, features)
        by_key = {(candidate.pattern_type, candidate.variant): candidate for candidate in candidates}
        self.assertEqual(by_key[("BRK-52WH", None)].pivot_price, _D("106"))
        self.assertEqual(by_key[("BRK-ATH", None)].pivot_price, _D("106"))
        for variant, lookback in (("BRK-2Y", 504), ("BRK-3Y", 756), ("BRK-5Y", 1260)):
            candidate = by_key[("BRK-MULTIY", variant)]
            self.assertEqual(candidate.measurements["resistance_lookback_sessions"], lookback)
            self.assertEqual(candidate.pivot_price, _D("106"))

    def test_range_source_requires_confirmed_tested_zone_in_20_to_120_session_window(self):
        bars, features, zone = _snapshot()
        bars[-1].update(close_price=_D("101"), high_price=_D("102"))
        self.assertIn("BRK-RANGE", {candidate.pattern_type for candidate in self._detect(bars, features, (zone,))})
        recent = PriceZone("recent", "INE000000001", ZoneType.RESISTANCE, bars[-20]["trading_date"], bars[-19]["trading_date"], _D("100"), _D("1"), _D("0"), ("a", "b"), 2, _D("0.5"), bars[-19]["trading_date"], bars[-19]["trading_date"])
        self.assertNotIn("BRK-RANGE", {candidate.pattern_type for candidate in self._detect(bars, features, (recent,))})
        old_bars, old_features, _ = _snapshot(150)
        old_bars[-1].update(close_price=_D("101"), high_price=_D("102"))
        old = PriceZone("old", "INE000000001", ZoneType.RESISTANCE, old_bars[0]["trading_date"], old_bars[0]["trading_date"], _D("100"), _D("1"), _D("0"), ("a", "b"), 2, _D("0.5"), old_bars[0]["trading_date"], old_bars[0]["trading_date"])
        self.assertNotIn("BRK-RANGE", {candidate.pattern_type for candidate in self._detect(old_bars, old_features, (old,))})

    def test_first_buffered_close_is_triggered_after_an_intermediate_close(self):
        bars, features, zone = _snapshot()
        bars[-2].update(close_price=_D("100.25"), high_price=_D("100.4"))
        bars[-1].update(close_price=_D("101"), high_price=_D("102"), volume=150)

        candidate = next(
            item for item in self._detect(bars, features, (zone,))
            if item.pattern_type == "BRK-RANGE"
        )

        self.assertEqual(PatternState.TRIGGERED, candidate.state)
        self.assertEqual(bars[-1]["trading_date"], candidate.measurements["breakout_date"])

    def test_breakout_quality_stays_anchored_to_trigger_and_source_base_is_linked(self):
        bars, features, zone = _snapshot()
        bars[-1].update(close_price=_D("101"), high_price=_D("102"), low_price=_D("99"), volume=150)
        source_base = {
            "pattern_instance_id": "base-1", "isin": "INE000000001",
            "pattern_type": "BASE-FLAT", "variant": None,
            "detected_date": bars[-2]["trading_date"],
            "pivot_price": _D("100"), "quality_score": _D("90"),
        }
        first = next(
            item for item in detect_breakouts(
                {"isin": "INE000000001"}, bars, features, (zone,), _context(bars),
                self.configuration, (source_base,),
            )
            if item.pattern_type == "BRK-RANGE"
        )
        first_components = first.measurements["quality_components"]

        day = bars[-1]["trading_date"] + timedelta(days=1)
        bars.append({
            **bars[-1], "trading_date": day, "close_price": _D("100.75"),
            "high_price": _D("101"), "low_price": _D("100"), "volume": 25,
        })
        features.append({
            **features[-1], "trading_date": day,
            "close_location_value": _D("0.1"), "relative_strength_percentile": _D("10"),
        })
        confirmed = next(
            item for item in detect_breakouts(
                {"isin": "INE000000001"}, bars, features, (zone,), _context(bars),
                self.configuration, (source_base,),
            )
            if item.pattern_type == "BRK-RANGE"
        )

        self.assertEqual(PatternState.CONFIRMED, confirmed.state)
        self.assertEqual(first_components, confirmed.measurements["quality_components"])
        self.assertEqual("base-1", confirmed.measurements["source_base_pattern_instance_id"])
        self.assertEqual(_D("90"), confirmed.measurements["source_base_quality"])

    def test_multi_year_resistance_age_uses_latest_historical_test(self):
        bars, features, _ = _snapshot(505)
        for row in bars[:-1]:
            row.update(high_price=_D("100"), close_price=_D("95"))
        bars[-11].update(high_price=_D("105"))
        bars[-1].update(high_price=_D("108"), low_price=_D("105"), close_price=_D("106"))

        candidate = next(
            item for item in self._detect(bars, features)
            if item.pattern_type == "BRK-MULTIY" and item.variant == "BRK-2Y"
        )

        self.assertEqual(9, candidate.measurements["resistance_age_sessions"])


if __name__ == "__main__": unittest.main()
