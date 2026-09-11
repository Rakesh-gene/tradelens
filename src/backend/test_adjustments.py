from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import unittest

from data_pipeline.adjustments import (
    AdjustmentRequest, AdjustmentService, CorporateActionAdjustmentError,
)


class AdjustmentRepository:
    def __init__(self, actions, bars=None):
        self.actions = actions
        self.bars = bars
        self.written = []

    def load_raw_bars(self, isin, from_date, to_date):
        return self.bars or [
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
        self.assertEqual(first_rows[0]["close_price"], Decimal("47.50"))
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

    def test_ignored_dividend_does_not_change_the_price_scale_version(self):
        repository = AdjustmentRepository([])
        request = AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1),
            cash_dividend_policy="ignore",
        )
        first = AdjustmentService(repository).rebuild(request)
        repository.actions = [{
            "source_event_key": "NSE:dividend:1", "action_type": "DIVIDEND",
            "ex_date": date(2021, 1, 1), "cash_value": Decimal("5"),
            "source_checksum": "new",
        }]
        second = AdjustmentService(repository).rebuild(request)

        self.assertNotEqual(first.action_set_checksum, second.action_set_checksum)
        self.assertEqual(first.adjustment_version, second.adjustment_version)

    def test_consolidation_adjusts_price_and_buyback_other_are_identity(self):
        identity_actions = [
            {"source_event_key": f"NSE:{kind}", "action_type": kind, "ex_date": date(2021, 1, 1), "source_checksum": kind}
            for kind in ("BUYBACK", "OTHER")
        ]
        repository = AdjustmentRepository(identity_actions + [{
            "source_event_key": "NSE:consolidation", "action_type": "CONSOLIDATION",
            "ex_date": date(2021, 1, 1), "numerator": Decimal("5"),
            "denominator": Decimal("1"), "source_checksum": "c",
        }])

        AdjustmentService(repository).rebuild(AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1),
            maximum_ex_date_jump_pct=Decimal("1000"),
        ))

        self.assertEqual(repository.written[0]["close_price"], Decimal("500.00"))
        self.assertEqual(repository.written[0]["volume"], 200)

    def test_rights_uses_issue_price_cum_close_and_entitlement_volume(self):
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:rights", "action_type": "RIGHTS",
            "ex_date": date(2021, 1, 1), "numerator": Decimal("1"),
            "denominator": Decimal("1"), "issue_price": Decimal("70"),
        }])

        AdjustmentService(repository).rebuild(AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1),
            maximum_ex_date_jump_pct=Decimal("100"),
        ))

        self.assertEqual(repository.written[0]["close_price"], Decimal("85.00"))
        self.assertEqual(repository.written[0]["volume"], 2000)

    def test_dividend_uses_cum_close_and_does_not_adjust_volume(self):
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:dividend", "action_type": "DIVIDEND",
            "ex_date": date(2021, 1, 1), "cash_value": Decimal("5"),
        }])

        AdjustmentService(repository).rebuild(AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1),
            cash_dividend_policy="adjust_price",
        ))

        self.assertEqual(repository.written[0]["close_price"], Decimal("95.00"))
        self.assertEqual(repository.written[0]["volume"], 1000)

    def test_composite_bonus_split_multiplies_both_terms(self):
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:composite", "action_type": "BONUS_SPLIT",
            "ex_date": date(2021, 1, 1), "numerator": Decimal("1"),
            "denominator": Decimal("1"), "old_face_value": Decimal("10"),
            "new_face_value": Decimal("2"),
        }])

        AdjustmentService(repository).rebuild(AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1),
            maximum_ex_date_jump_pct=Decimal("100"),
        ))

        self.assertEqual(repository.written[0]["close_price"], Decimal("10.00"))
        self.assertEqual(repository.written[0]["volume"], 10000)

    def test_unresolved_material_action_is_not_silently_ignored(self):
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:demerger", "action_type": "DEMERGER",
            "ex_date": date(2021, 1, 1),
        }])

        with self.assertRaisesRegex(CorporateActionAdjustmentError, "reviewed manual"):
            AdjustmentService(repository).rebuild(AdjustmentRequest(
                "INE000000001", date(2020, 1, 1), date(2021, 1, 1)
            ))

    def test_reviewed_factor_resolves_non_deterministic_action(self):
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:demerger", "action_type": "DEMERGER",
            "ex_date": date(2021, 1, 1), "manual_price_factor": Decimal("0.5"),
            "manual_volume_factor": Decimal("1"),
        }])

        AdjustmentService(repository).rebuild(AdjustmentRequest(
            "INE000000001", date(2020, 1, 1), date(2021, 1, 1)
        ))

        self.assertEqual(repository.written[0]["close_price"], Decimal("50.00"))
        self.assertEqual(repository.written[0]["volume"], 1000)

    def test_nse_raw_previous_close_does_not_auto_resolve_demerger(self):
        bars = [
            {"isin": "INE000000001", "trading_date": date(2020, 1, 1),
             "open_price": Decimal("100"), "high_price": Decimal("100"),
             "low_price": Decimal("100"), "close_price": Decimal("100"),
             "volume": 1000, "raw_revision": 1},
            {"isin": "INE000000001", "trading_date": date(2021, 1, 1),
             "open_price": Decimal("61"), "high_price": Decimal("62"),
             "low_price": Decimal("59"), "close_price": Decimal("60"),
             "previous_close_price": Decimal("60"), "volume": 1000,
             "raw_revision": 1},
        ]
        repository = AdjustmentRepository([{
            "source_event_key": "NSE:demerger", "action_type": "DEMERGER",
            "ex_date": date(2021, 1, 1),
        }], bars)

        with self.assertRaisesRegex(
            CorporateActionAdjustmentError, "reviewed manual adjustment factor"
        ):
            AdjustmentService(repository).rebuild(AdjustmentRequest(
                "INE000000001", date(2020, 1, 1), date(2021, 1, 1)
            ))


if __name__ == "__main__":
    unittest.main()
