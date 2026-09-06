from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from operations.recovery import RecoveryService
from pattern_engine.runner import PatternEngineVersions


class RecoveryServiceTestCase(unittest.TestCase):
    def test_rebuild_scans_the_latest_available_trading_session_not_a_weekend(self):
        market = SimpleNamespace(
            get_raw_bar_date_range=lambda isin: (date(2016, 9, 6), date(2026, 9, 4)),
            load_benchmark_snapshot=lambda start, end: {"bars": []},
        )
        class Runner:
            def __init__(self): self.calls = []
            def run_security(self, isin, as_of, versions, *, initiated_by):
                self.calls.append((isin, as_of, versions, initiated_by))
                return SimpleNamespace(
                    run_id="scan-1", status=SimpleNamespace(value="COMPLETED"),
                    metrics={"candidatesDetected": 1},
                )
        runner = Runner()
        configuration = SimpleNamespace(section=lambda name: {
            "cash_dividend_policy": "ignore", "source_mode": "TRADELENS_REBUILT",
        })
        adjusted = SimpleNamespace(adjustment_version="v1:adjusted")

        with patch("operations.recovery.AdjustmentService") as adjustments, \
             patch("operations.recovery.FeatureService") as features, \
             patch("operations.recovery.SwingZoneService") as swings:
            adjustments.return_value.rebuild.return_value = adjusted
            result = RecoveryService(market, runner, configuration).rebuild_security(
                "INE002A01018", date(2016, 9, 5), date(2026, 9, 5),
                PatternEngineVersions("v1", "v1", "v1"),
            )

        request = adjustments.return_value.rebuild.call_args.args[0]
        self.assertEqual(date(2026, 9, 4), request.to_date)
        self.assertEqual(date(2026, 9, 4), features.return_value.rebuild.call_args.args[2])
        self.assertEqual(date(2026, 9, 4), runner.calls[0][1])
        self.assertEqual(date(2026, 9, 4), result["asOf"])


if __name__ == "__main__":
    unittest.main()
