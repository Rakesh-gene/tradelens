from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.base_detectors import detect_primary_bases
from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import PatternState, SwingType, ZoneType
from pattern_engine.models import DetectionContext, PriceZone, SwingPoint


def _rows(count: int, *, close: Decimal = Decimal("108")):
    start = date(2025, 1, 1)
    bars, features = [], []
    for index in range(count):
        day = start + timedelta(days=index)
        bars.append({"isin": "INE000000001", "trading_date": day, "open_price": close, "high_price": max(Decimal("110"), close), "low_price": min(Decimal("100"), close), "close_price": close, "volume": 1000 if index < count * 2 // 3 else 500})
        features.append({"isin": "INE000000001", "trading_date": day, "atr_14": Decimal("2") if index < count * 2 // 3 else Decimal("1"), "atr_10": Decimal("2") if index < count * 2 // 3 else Decimal("1"), "sma_50": Decimal("105"), "sma_200": Decimal("100"), "sma_50_slope": Decimal("1"), "relative_strength_percentile": Decimal("90")})
    return bars, features


def _context(bars): return DetectionContext(bars[-1]["trading_date"], {}, None, (), "v1")


class PrimaryBaseDetectorTestCase(unittest.TestCase):
    def setUp(self): self.configuration = load_pattern_engine_configuration()

    def test_flat_base_has_zone_geometry_components_and_ready_boundary(self):
        bars, features = _rows(60)
        start, end = bars[-20]["trading_date"], bars[-1]["trading_date"]
        zones = [
            PriceZone("r", "INE000000001", ZoneType.RESISTANCE, start, end, Decimal("110"), Decimal("1"), Decimal("0"), ("a", "b"), 2, Decimal("0.5"), end, end),
            PriceZone("s", "INE000000001", ZoneType.SUPPORT, start, end, Decimal("100"), Decimal("1"), Decimal("0"), ("c", "d"), 2, Decimal("0.5"), end, end),
        ]
        swings = [SwingPoint(key, "INE000000001", start, end, kind, price, Decimal(1), None, True) for key, kind, price in (("a", SwingType.HIGH, Decimal(110)), ("b", SwingType.HIGH, Decimal(110)), ("c", SwingType.LOW, Decimal(100)), ("d", SwingType.LOW, Decimal(100)))]
        candidates = detect_primary_bases({"isin": "INE000000001"}, bars, features, swings, zones, _context(bars), self.configuration)
        flat = next(candidate for candidate in candidates if candidate.pattern_type == "BASE-FLAT")

        self.assertEqual(flat.state, PatternState.READY)
        self.assertEqual(flat.pivot_price, Decimal("110"))
        self.assertEqual(flat.measurements["resistance_tests"], 2)
        self.assertIn("flatness", flat.measurements["quality_components"])

        bars[-1]["close_price"] = Decimal("98")
        bars[-1]["low_price"] = Decimal("98")
        invalid = next(candidate for candidate in detect_primary_bases({"isin": "INE000000001"}, bars, features, (), zones, _context(bars), self.configuration) if candidate.pattern_type == "BASE-FLAT")
        self.assertEqual(invalid.state, PatternState.INVALIDATED)

    def test_52_week_high_excludes_current_bar_and_derives_ready_and_strong_ready(self):
        bars, features = _rows(253, close=Decimal("117"))
        bars[-40]["high_price"] = Decimal("120")
        bars[-1]["high_price"] = Decimal("117")
        candidates = detect_primary_bases({"isin": "INE000000001"}, bars, features, (), (), _context(bars), self.configuration)
        base = next(candidate for candidate in candidates if candidate.pattern_type == "BASE-52WH")

        self.assertEqual(base.pivot_price, Decimal("120"))
        self.assertEqual(base.state, PatternState.READY)
        self.assertFalse(base.measurements["strong_ready"])

    def test_vcp_boundaries_and_one_session_lifecycle_states(self):
        bars, features = _rows(90, close=Decimal("97.5"))
        start = bars[0]["trading_date"]
        for bar in bars[10:]: bar["low_price"] = Decimal("94")
        swings = [
            SwingPoint("h1", "INE000000001", start + timedelta(days=10), start + timedelta(days=13), SwingType.HIGH, Decimal("110"), Decimal("1"), None, True),
            SwingPoint("l1", "INE000000001", start + timedelta(days=20), start + timedelta(days=23), SwingType.LOW, Decimal("98"), Decimal("1"), None, True),
            SwingPoint("h2", "INE000000001", start + timedelta(days=30), start + timedelta(days=33), SwingType.HIGH, Decimal("100"), Decimal("1"), None, True),
            SwingPoint("l2", "INE000000001", start + timedelta(days=40), start + timedelta(days=43), SwingType.LOW, Decimal("94"), Decimal("1"), None, True),
            SwingPoint("h3", "INE000000001", start + timedelta(days=50), start + timedelta(days=53), SwingType.HIGH, Decimal("98"), Decimal("1"), None, True),
            SwingPoint("l3", "INE000000001", start + timedelta(days=60), start + timedelta(days=63), SwingType.LOW, Decimal("95"), Decimal("1"), None, True),
        ]
        zone = PriceZone("r", "INE000000001", ZoneType.RESISTANCE, start + timedelta(days=40), start + timedelta(days=63), Decimal("98"), Decimal("1"), Decimal("0"), ("h3",), 2, Decimal("0.5"), start + timedelta(days=60), start + timedelta(days=63))
        ready = next(candidate for candidate in detect_primary_bases({"isin": "INE000000001"}, bars, features, swings, (zone,), _context(bars), self.configuration) if candidate.pattern_type == "BASE-VCP")

        self.assertEqual(ready.variant, "VCP-3C")
        self.assertEqual(ready.state, PatternState.READY)
        self.assertEqual(ready.measurements["contraction_count"], 3)
        self.assertEqual(len(ready.measurements["contractions_pct"]), 3)
        self.assertEqual(ready.measurements["pivot_source"], "resistance_zone")

        bars[-2]["close_price"] = Decimal("99")
        bars[-1]["close_price"] = Decimal("99")
        confirmed = next(candidate for candidate in detect_primary_bases({"isin": "INE000000001"}, bars, features, swings, (zone,), _context(bars), self.configuration) if candidate.pattern_type == "BASE-VCP")
        self.assertEqual(confirmed.state, PatternState.CONFIRMED)

        self.assertIsNone(next((candidate for candidate in detect_primary_bases({"isin": "INE000000001"}, bars, features, swings[:2], (zone,), _context(bars), self.configuration) if candidate.pattern_type == "BASE-VCP"), None))


if __name__ == "__main__": unittest.main()
