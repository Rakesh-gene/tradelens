from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest

from repositories.watchlists import InMemoryWatchlistRepository
from watchlist.service import WATCHLIST_LIMIT, WatchlistService


class WatchlistServiceTestCase(unittest.TestCase):
    def test_items_are_isolated_idempotent_and_removable(self):
        repository = InMemoryWatchlistRepository([
            {"isin": "INE002A01018", "symbol": "RELIANCE", "company_name": "Reliance Industries Limited"},
        ])
        service = WatchlistService(repository)

        self.assertTrue(service.add("user-1", "ine002a01018")["added"])
        self.assertFalse(service.add("user-1", "INE002A01018")["added"])
        self.assertEqual(1, service.list("user-1")["count"])
        self.assertEqual(0, service.list("user-2")["count"])
        self.assertTrue(service.remove("user-1", "INE002A01018")["removed"])
        self.assertFalse(service.remove("user-1", "INE002A01018")["removed"])

    def test_rejects_invalid_or_unknown_securities(self):
        service = WatchlistService(InMemoryWatchlistRepository([]))
        with self.assertRaisesRegex(ValueError, "valid ISIN"):
            service.add("user-1", "RELIANCE")
        with self.assertRaisesRegex(LookupError, "Security not found"):
            service.add("user-1", "INE002A01018")

    def test_limit_is_enforced(self):
        repository = InMemoryWatchlistRepository()
        service = WatchlistService(repository)
        for index in range(WATCHLIST_LIMIT):
            service.add("user-1", f"IN{index:09d}0")
        with self.assertRaisesRegex(ValueError, "at most 100"):
            service.add("user-1", "IN9999999990")

    def test_enriched_items_are_grouped_and_include_recent_activity(self):
        repository = InMemoryWatchlistRepository([
            {
                "isin": "INE002A01018", "symbol": "RELIANCE", "company_name": "Reliance Industries Limited",
                "data_as_of": date(2026, 9, 11), "last_close": Decimal("98"), "previous_close": Decimal("96"),
                "ema_20": Decimal("95"), "sma_50": Decimal("90"), "sma_200": Decimal("80"),
                "relative_strength_1m": Decimal("3"), "relative_strength_3m": Decimal("8"),
                "relative_strength_6m": Decimal("12"), "relative_strength_12m": Decimal("18"),
                "relative_strength_percentile": Decimal("92"),
                "sector_relative_strength": Decimal("5.5"), "sector_strength_score": Decimal("74"),
                "pattern_id": "pattern-1", "pattern_type": "BASE-VCP", "variant": "VCP-3C",
                "state": "READY", "setup_score": Decimal("84"), "pivot_price": Decimal("100"),
                "support_price": Decimal("92"), "invalidation_price": Decimal("89"),
            },
        ], events=[{
            "event_id": "event-1", "pattern_instance_id": "pattern-1", "event_type": "STATE_CHANGED",
            "effective_date": date(2026, 9, 11), "previous_state": "MATURE", "new_state": "READY",
            "isin": "INE002A01018", "symbol": "RELIANCE", "company_name": "Reliance Industries Limited",
            "pattern_type": "BASE-VCP", "variant": "VCP-3C",
        }])
        service = WatchlistService(repository)
        service.add("user-1", "INE002A01018")

        payload = service.list("user-1")

        self.assertEqual("NEAR_BREAKOUT", payload["items"][0]["attentionGroup"])
        self.assertAlmostEqual(2.083333, payload["items"][0]["dailyChangePct"], places=5)
        self.assertEqual(-2.0, payload["items"][0]["primarySetup"]["distanceToPivotPct"])
        self.assertEqual(Decimal("92"), payload["items"][0]["relativeStrengthPercentile"])
        self.assertEqual(Decimal("5.5"), payload["items"][0]["sectorContext"]["relativeStrength"])
        self.assertAlmostEqual(3 - 8 / 3, payload["items"][0]["rotation"]["momentum"])
        self.assertEqual("LEADING", payload["items"][0]["rotation"]["zone"])
        self.assertEqual(1, next(group for group in payload["groups"] if group["id"] == "NEAR_BREAKOUT")["count"])
        self.assertEqual("RELIANCE", payload["activity"][0]["security"]["symbol"])

    def test_migration_has_user_and_security_keys(self):
        migration = (Path(__file__).parent / "migrations" / "033_create_user_watchlist.sql").read_text(encoding="utf-8")
        self.assertIn("PRIMARY KEY (user_id, isin)", migration)
        self.assertIn("REFERENCES users (id) ON DELETE CASCADE", migration)
        self.assertIn("REFERENCES nse_equities (isin) ON DELETE CASCADE", migration)

    def test_quadrant_reconciliation_records_entry_change_and_exit_once(self):
        repository = InMemoryWatchlistRepository([{
            "isin": "INE002A01018", "symbol": "RELIANCE", "company_name": "Reliance Industries Limited",
            "data_as_of": date(2026, 9, 9), "relative_strength_1m": Decimal("6"),
            "relative_strength_3m": Decimal("9"),
        }])
        service = WatchlistService(repository)
        service.add("user-1", "INE002A01018")

        self.assertEqual(1, repository.reconcile_quadrants(date(2026, 9, 9)))
        self.assertEqual(0, repository.reconcile_quadrants(date(2026, 9, 9)))
        repository._securities["INE002A01018"].update(
            data_as_of=date(2026, 9, 10), relative_strength_1m=Decimal("1")
        )
        self.assertEqual(1, repository.reconcile_quadrants(date(2026, 9, 10)))
        repository._securities["INE002A01018"].update(
            data_as_of=date(2026, 9, 11), relative_strength_1m=None,
            relative_strength_3m=None,
        )
        self.assertEqual(1, repository.reconcile_quadrants(date(2026, 9, 11)))

        activity = service.list("user-1")["activity"]
        self.assertEqual(["QUADRANT_LEFT", "QUADRANT_CHANGED", "QUADRANT_ENTERED"],
                         [event["eventType"] for event in activity])
        self.assertEqual("QUADRANT", activity[0]["activityType"])
        self.assertEqual("WEAKENING", activity[0]["previousZone"])

    def test_quadrant_tracking_migration_is_notification_ready(self):
        migration = (Path(__file__).parent / "migrations" / "034_track_watchlist_quadrant_events.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS watchlist_quadrant_state", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS watchlist_quadrant_events", migration)
        self.assertIn("UNIQUE (user_id, isin, effective_date)", migration)


if __name__ == "__main__":
    unittest.main()
