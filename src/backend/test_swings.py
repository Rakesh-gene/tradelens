from __future__ import annotations

from datetime import date
from decimal import Decimal
import unittest

from pattern_engine.enums import SwingType
from pattern_engine.models import SwingPoint
from pattern_engine.swings import SwingZoneService, build_price_zones, detect_swings


def _bar(day: date, high: int, low: int) -> dict[str, object]:
    return {"isin": "INE000000001", "trading_date": day, "high_price": Decimal(high), "low_price": Decimal(low)}


class _SwingRepository:
    def __init__(self, bars):
        self.bars = bars
        self.swings = []
        self.zones = []

    def load_adjusted_bars(self, *args):
        return self.bars

    def load_technical_features(self, *args):
        return []

    def load_swing_points(self, isin, from_date, to_date, feature_version, **kwargs):
        return [row for row in self.swings if row["feature_version"] == feature_version]

    def load_price_zones(self, isin, from_date, to_date, feature_version, **kwargs):
        return [row for row in self.zones if row["feature_version"] == feature_version]

    def upsert_swing_points(self, rows):
        self.swings.extend(dict(row) for row in rows)
        return len(rows)

    def upsert_price_zones(self, rows):
        self.zones.extend(dict(row) for row in rows)
        return len(rows)


class SwingAndZoneTestCase(unittest.TestCase):
    def test_persisted_ids_are_distinct_by_feature_version_and_stable_on_rerun(self) -> None:
        sessions = [date(2026, 1, day) for day in (2, 5, 6, 7, 9, 12, 13)]
        repository = _SwingRepository([
            _bar(day, high, low)
            for day, high, low in zip(sessions, (91, 92, 93, 100, 94, 95, 96), (86, 87, 88, 89, 88, 87, 86))
        ])
        service = SwingZoneService(repository)

        service.rebuild("INE000000001", sessions[0], sessions[-1], "adjusted-v1", "features-v1", "data-v1")
        first_swing_id = repository.swings[-1]["id"]
        first_zone_id = repository.zones[-1]["id"]
        service.rebuild("INE000000001", sessions[0], sessions[-1], "adjusted-v1", "features-v2", "data-v1")
        second_swing_id = repository.swings[-1]["id"]
        second_zone_id = repository.zones[-1]["id"]

        self.assertNotEqual(first_swing_id, second_swing_id)
        self.assertNotEqual(first_zone_id, second_zone_id)
        self.assertEqual(repository.zones[-1]["source_swing_ids"], (second_swing_id,))

        service.rebuild("INE000000001", sessions[0], sessions[-1], "adjusted-v1", "features-v1", "data-v1")
        self.assertEqual(repository.swings[-1]["id"], first_swing_id)
        self.assertEqual(repository.zones[-1]["id"], first_zone_id)

    def test_pivot_is_invisible_until_third_subsequent_trading_session(self) -> None:
        sessions = [date(2026, 1, day) for day in (2, 5, 6, 7, 9, 12, 13)]  # Jan 8 is a non-trading weekday
        bars = [_bar(day, high, low) for day, high, low in zip(sessions, (91, 92, 93, 100, 94, 95, 96), (86, 87, 88, 89, 88, 87, 86))]

        self.assertEqual(detect_swings(bars, as_of=date(2026, 1, 12)), [])
        swings = detect_swings(bars, as_of=date(2026, 1, 13))
        self.assertEqual(len(swings), 1)
        self.assertEqual(swings[0].pivot_date, date(2026, 1, 7))
        self.assertEqual(swings[0].confirmation_date, date(2026, 1, 13))

    def test_small_alternating_oscillation_is_persisted_raw_but_not_meaningful(self) -> None:
        days = [date(2026, 2, day) for day in range(1, 15)]
        highs = (90, 91, 92, 100, 93, 94, 95, 96, 97, 98, 99, 101, 98, 97)
        lows = (99, 99, 99, 99, 99, 99, 99, 98, 99, 99, 99, 99, 99, 99)
        swings = detect_swings([_bar(day, high, low) for day, high, low in zip(days, highs, lows)])

        low = next(swing for swing in swings if swing.swing_type is SwingType.LOW)
        self.assertFalse(low.is_meaningful)
        self.assertLess(low.move_size_pct, Decimal("4"))

    def test_nearby_resistance_points_cluster_deterministically(self) -> None:
        source = [
            SwingPoint("a", "INE000000001", date(2026, 1, 2), date(2026, 1, 5), SwingType.HIGH, Decimal("499"), Decimal("2"), None, True),
            SwingPoint("b", "INE000000001", date(2026, 1, 7), date(2026, 1, 10), SwingType.HIGH, Decimal("502"), Decimal("2"), None, True),
            SwingPoint("c", "INE000000001", date(2026, 1, 12), date(2026, 1, 15), SwingType.HIGH, Decimal("500"), Decimal("2"), None, True),
        ]
        zones = build_price_zones(source)
        reversed_zones = build_price_zones(list(reversed(source)))

        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].median_price, Decimal("500"))
        self.assertEqual(zones[0].test_count, 3)
        self.assertEqual(zones[0].last_test_date, date(2026, 1, 12))
        self.assertEqual(zones[0].confirmation_date, date(2026, 1, 15))
        self.assertEqual(zones[0].breakout_buffer_pct, Decimal("0.5"))
        self.assertEqual(zones, reversed_zones)

    def test_zone_lookback_and_confirmation_boundaries_are_enforced(self) -> None:
        source = [
            SwingPoint("old", "INE000000001", date(2025, 1, 2), date(2025, 1, 7), SwingType.HIGH, Decimal("500"), Decimal("2"), None, True),
            SwingPoint("future", "INE000000001", date(2026, 1, 2), date(2026, 1, 7), SwingType.HIGH, Decimal("501"), Decimal("2"), None, True),
        ]

        self.assertEqual(build_price_zones(source, lookback_start=date(2026, 1, 1), as_of=date(2026, 1, 6)), [])
        zones = build_price_zones(source, lookback_start=date(2026, 1, 1), as_of=date(2026, 1, 7))
        self.assertEqual(zones[0].source_swing_ids, ("future",))


if __name__ == "__main__":
    unittest.main()
