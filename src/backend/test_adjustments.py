from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import unittest

from data_pipeline.adjustments import AdjustmentRequest, AdjustmentService


class AdjustmentRepository:
    def __init__(self, actions):
        self.actions = actions
        self.written = []

    def load_raw_bars(self, isin, from_date, to_date):
        return [
            {"isin": isin, "trading_date": date(2020, 1, 1), "open_price": Decimal("100"),
             "high_price": Decimal("110"), "low_price": Decimal("90"), "close_price": Decimal("100"),
             "volume": 1000, "raw_revision": 1},
            {"isin": isin, "trading_date": date(2021, 1, 1), "open_price": Decimal("50"),
             "high_price": Decimal("55"), "low_price": Decimal("45"), "close_price": Decimal("50"),
             "volume": 2000, "raw_revision": 2},
        ]

    def load_corporate_actions(self, isin, from_date, to_date, *, as_of=None):
        return self.actions

    def upsert_adjusted_bars(self, bars):
        self.written = bars
        return len(bars)


class AdjustmentServiceTestCase(unittest.TestCase):
    def test_split_adjusts_only_pre_ex_date_prices_and_inverts_volume(self):
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:split:1", "action_type": "SPLIT", "ex_date": date(2021, 1, 1),
            "numerator": Decimal("1"), "denominator": Decimal("2"), "source_checksum": "a",
        }])

        result = AdjustmentService(repository).rebuild(AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1), "v1"
        ))

        self.assertEqual(repository.written[0]["close_price"], Decimal("50.00"))
        self.assertEqual(repository.written[0]["volume"], 2000)
        self.assertEqual(repository.written[1]["close_price"], Decimal("50.00"))
        self.assertEqual(repository.written[1]["price_adjustment_factor"], Decimal("1"))
        self.assertEqual(result.rows_written, 2)
        self.assertTrue(result.adjustment_version.startswith("v1:"))

    def test_bonus_and_dividend_policy_are_deterministic_and_point_in_time_is_passed(self):
        actions = [
            {"source_event_key": "NSE:bonus:1", "action_type": "BONUS", "ex_date": date(2021, 1, 1),
             "numerator": Decimal("1"), "denominator": Decimal("1"), "source_checksum": "b"},
            {"source_event_key": "NSE:dividend:1", "action_type": "DIVIDEND", "ex_date": date(2021, 1, 1),
             "cash_value": Decimal("5"), "source_checksum": "d"},
        ]
        repository = AdjustmentRepository(actions)
        request = AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1), "v1",
            as_of=datetime(2021, 2, 1), cash_dividend_policy="adjust_price",
        )

        first = AdjustmentService(repository).rebuild(request)
        first_rows = list(repository.written)
        second = AdjustmentService(repository).rebuild(request)

        self.assertEqual(first.action_set_checksum, second.action_set_checksum)
        self.assertEqual(first.adjustment_version, second.adjustment_version)
        self.assertEqual(first_rows[0]["close_price"], Decimal("45.00"))
        self.assertEqual(first_rows[0]["action_set_checksum"], first.action_set_checksum)

    def test_revised_action_changes_version_without_mutating_raw_input(self):
        original = [{"source_event_key": "NSE:bonus:1", "action_type": "BONUS", "ex_date": date(2021, 1, 1),
                     "numerator": Decimal("1"), "denominator": Decimal("1"), "source_checksum": "old"}]
        revised = [{**original[0], "source_checksum": "new", "denominator": Decimal("2")}]
        repository = AdjustmentRepository(original)
        first = AdjustmentService(repository).rebuild(AdjustmentRequest("INE000000001", date(2020, 1, 1), date(2021, 1, 1)))
        repository.actions = revised
        second = AdjustmentService(repository).rebuild(AdjustmentRequest("INE000000001", date(2020, 1, 1), date(2021, 1, 1)))

        self.assertNotEqual(first.adjustment_version, second.adjustment_version)
        self.assertEqual(original[0]["denominator"], Decimal("1"))

    def test_nse_source_mode_does_not_apply_actions_twice(self):
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:split:1", "action_type": "SPLIT", "ex_date": date(2021, 1, 1),
            "numerator": Decimal("1"), "denominator": Decimal("2"), "source_checksum": "a",
        }])

        AdjustmentService(repository).rebuild(AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1), source_mode="NSE_SOURCE"
        ))

        self.assertEqual(repository.written[0]["close_price"], Decimal("100.00"))
        self.assertEqual(repository.written[0]["adjustment_source"], "NSE_SOURCE")

    def test_database_lineage_does_not_change_the_action_set_version(self):
        action = {"source_event_key": "NSE:split:1", "action_type": "SPLIT", "ex_date": date(2021, 1, 1),
                  "numerator": Decimal("1"), "denominator": Decimal("2"), "source_checksum": "a"}
        repository = AdjustmentRepository([{**action, "import_run_id": "run-one"}])
        first = AdjustmentService(repository).rebuild(AdjustmentRequest("INE000000001", date(2020, 1, 1), date(2021, 1, 1)))
        repository.actions = [{**action, "import_run_id": "run-two"}]
        second = AdjustmentService(repository).rebuild(AdjustmentRequest("INE000000001", date(2020, 1, 1), date(2021, 1, 1)))

        self.assertEqual(first.action_set_checksum, second.action_set_checksum)
        self.assertEqual(first.adjustment_version, second.adjustment_version)

    def test_consolidation_adjusts_price_and_rights_buyback_other_are_identity(self):
        identity_actions = [
            {"source_event_key": f"NSE:{kind}", "action_type": kind, "ex_date": date(2021, 1, 1), "source_checksum": kind}
            for kind in ("RIGHTS", "BUYBACK", "OTHER")
        ]
        repository = AdjustmentRepository(identity_actions + [{
            "source_event_key": "NSE:consolidation", "action_type": "CONSOLIDATION",
            "ex_date": date(2021, 1, 1), "numerator": Decimal("5"),
            "denominator": Decimal("1"), "source_checksum": "c",
        }])

        AdjustmentService(repository).rebuild(AdjustmentRequest("INE000000001", date(2020, 1, 1), date(2021, 1, 1)))

        self.assertEqual(repository.written[0]["close_price"], Decimal("500.00"))
        self.assertEqual(repository.written[0]["volume"], 200)


if __name__ == "__main__":
    unittest.main()
