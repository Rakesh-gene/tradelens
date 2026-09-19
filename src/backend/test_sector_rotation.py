from datetime import date, timedelta
import unittest

from pattern_engine.query_service import PatternQueryService, browser_payload
from pattern_engine.sector_rotation import zone
from repositories.pattern_queries import InMemoryPatternQueryRepository


class SectorRotationTests(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2026, 9, 10)
        securities = [{"isin": f"INE{i:09d}", "symbol": f"S{i}", "company_name": f"Stock {i}",
                       "sector_code": "TECH", "sector_name": "Technology"} for i in range(4)]
        features = [{"isin": securities[0]["isin"], "trading_date": self.as_of - timedelta(days=i),
                     "relative_strength_1m": 10, "relative_strength_3m": 10 if i == 0 else 5} for i in range(21)]
        features += [{"isin": securities[1]["isin"], "trading_date": self.as_of, "relative_strength_3m": 30},
                     {"isin": securities[2]["isin"], "trading_date": self.as_of - timedelta(days=1), "relative_strength_3m": 99}]
        self.repository = InMemoryPatternQueryRepository(securities=securities, features=features)
        self.service = PatternQueryService(self.repository)

    def test_quadrants_and_missing_values(self):
        for x, y, expected in [(1, 1, "LEADING"), (1, -1, "WEAKENING"), (-1, -1, "LAGGING"), (-1, 1, "IMPROVING"), (0, 0, "LEADING"), (None, 1, "UNAVAILABLE"), (1, None, "UNAVAILABLE")]:
            self.assertEqual(expected, zone(x, y))

    def test_same_date_coverage_and_matched_momentum(self):
        result = browser_payload(self.service.sector_rotation({"asOf": [self.as_of.isoformat()]}))
        sector = result["items"][0]
        self.assertEqual(20, sector["rs3m"])
        self.assertAlmostEqual(10 - 10 / 3, sector["momentum"])
        self.assertEqual(2, sector["coveredCount"])
        self.assertEqual(1, sector["pairedCount"])
        self.assertTrue(sector["isPartial"])
        self.assertEqual(5, len(sector["trail"]))
        self.assertEqual((self.as_of - timedelta(days=4)).isoformat(), sector["trail"][0]["date"])
        self.assertEqual(self.as_of.isoformat(), sector["trail"][-1]["date"])

    def test_missing_short_horizon_does_not_fabricate_rotation(self):
        self.repository.features[0]["relative_strength_1m"] = None
        sector = self.service.sector_rotation({"asOf": [self.as_of.isoformat()]})["items"][0]
        self.assertIsNone(sector["momentum"])
        self.assertEqual("UNAVAILABLE", sector["zone"])

    def test_ranked_pagination_and_missing_last(self):
        query = {"asOf": [self.as_of.isoformat()], "sector": ["TECH"], "pageSize": ["2"]}
        first = self.service.sector_stocks(query)
        self.assertEqual([30, 10], [s["rs3m"] for s in first["items"]])
        second = self.service.sector_stocks({**query, "cursor": [first["nextCursor"]]})
        self.assertEqual([None, None], [s["rank"] for s in second["items"]])
        self.assertIsNone(second["nextCursor"])

    def test_validation_and_no_future_data(self):
        with self.assertRaises(ValueError):
            self.service.sector_stocks({"sector": ["TECH"]})
        result = self.service.sector_rotation({"asOf": [(self.as_of - timedelta(days=50)).isoformat()]})
        self.assertEqual([], result["items"])
        self.assertTrue(result["isStale"])

    def test_new_membership_has_no_reconstructed_history(self):
        for security in self.repository.securities.values():
            security["effective_from"] = self.as_of
        result = self.service.sector_rotation({"asOf": [(self.as_of - timedelta(days=1)).isoformat()]})
        self.assertEqual([], result["items"])
