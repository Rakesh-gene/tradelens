from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import ImportStatus, PatternClass, PatternState
from pattern_engine.models import PatternCandidate
from pattern_engine.runner import PatternEngineRunner, PatternEngineVersions, PatternScanMode
from repositories.patterns import InMemoryPatternRepository


_D = Decimal
_VERSIONS = PatternEngineVersions("engine-v1", "features-v1", "adjusted-v1")


class FakeDataSource:
    def __init__(self, isins=("GOOD",), affected=()):
        self.securities = [{"isin": isin, "symbol": isin} for isin in isins]
        self.affected = list(affected)

    def list_eligible_securities(self):
        return list(self.securities)

    def list_affected_security_dates(self, run_id):
        return list(self.affected)

    def load_adjusted_bars(self, isin, from_date, to_date, adjustment_version):
        start = to_date - timedelta(days=249)
        return [
            {
                "isin": isin, "trading_date": start + timedelta(days=index),
                "open_price": _D("99"), "high_price": _D("102"),
                "low_price": _D("98"), "close_price": _D("100"), "volume": 1000,
            }
            for index in range(250)
        ]

    def load_technical_features(self, isin, from_date, to_date, feature_version):
        start = to_date - timedelta(days=249)
        return [
            {
                "isin": isin, "trading_date": start + timedelta(days=index),
                "ema_20": _D("95"), "sma_50": _D("90"), "sma_200": _D("80"),
                "ema_20_slope": _D("1"), "sma_50_slope": _D("1"),
                "relative_strength_percentile": _D("80"),
                "volume_ratio_20": _D("1"), "median_volume_20": _D("1000"),
                "median_traded_value_20": _D("25000000"),
            }
            for index in range(250)
        ]

    def load_swing_points(self, *args, **kwargs):
        return []

    def load_price_zones(self, *args, **kwargs):
        return []

    def load_benchmark_snapshot(self, from_date, as_of_date):
        return {"market_regime_score": _D("70")}

    def load_sector_snapshot(self, isin, as_of_date):
        return {"sector_strength_score": _D("75")}


class FakeRunRepository:
    def __init__(self):
        self.created = []
        self.updated = []
        self.metrics = []
        self.failures = []

    def create_import_run(self, job_type, initiated_by, **values):
        self.created.append((job_type, initiated_by, values))
        return "scan-run-1"

    def update_import_run(self, run_id, status, **values):
        self.updated.append((run_id, status, values))

    def update_pattern_scan_metrics(self, run_id, metrics):
        self.metrics.append((run_id, dict(metrics)))

    def record_pattern_scan_failure(self, failure):
        self.failures.append(dict(failure))


def _candidate(isin, as_of):
    return PatternCandidate(
        isin, PatternClass.TREND, "TREND-S2", None, as_of, as_of, as_of,
        PatternState.DETECTED, _D("80"), _D("60"), None, None,
        None, None, None, {"evidence": "synthetic"}, ("TREND-S2",), None,
    )


class PatternEngineRunnerTestCase(unittest.TestCase):
    def setUp(self):
        self.configuration = load_pattern_engine_configuration()
        self.patterns = InMemoryPatternRepository()
        self.runs = FakeRunRepository()

    def _runner(self, data):
        return PatternEngineRunner(data, self.patterns, self.runs, self.configuration)

    def _detector_patches(self, supporting):
        return (
            patch("pattern_engine.runner.detect_supporting_patterns", side_effect=supporting),
            patch("pattern_engine.runner.detect_primary_bases", return_value=[]),
            patch("pattern_engine.runner.detect_breakouts", return_value=[]),
            patch("pattern_engine.runner.detect_pullbacks", return_value=[]),
            patch("pattern_engine.runner.detect_failures", return_value=[]),
        )

    def test_index_scan_does_not_require_equity_volume_fields(self):
        runner = self._runner(FakeDataSource())
        as_of = date(2026, 9, 5)
        bars = [{"trading_date": as_of, "close_price": _D("100")} for _ in range(200)]
        features = [{"trading_date": as_of, "median_traded_value_20": _D("0"), "median_volume_20": _D("0")}]

        decisions = runner._eligibility_decisions(
            bars, features, as_of, {"instrumentType": "INDEX"}
        )

        self.assertNotIn("median_traded_value_20", {item["rule"] for item in decisions})
        self.assertNotIn("median_volume_20", {item["rule"] for item in decisions})

    def test_dry_run_reports_stage_decisions_and_scores_without_live_writes(self):
        as_of = date(2026, 9, 5)
        calls = []

        def supporting(security, *args):
            calls.append("supporting")
            return [_candidate(str(security["isin"]), as_of)]

        def empty_stage(name):
            def detect(*args, **kwargs):
                calls.append(name)
                return []
            return detect

        with (
            patch("pattern_engine.runner.detect_supporting_patterns", side_effect=supporting),
            patch("pattern_engine.runner.detect_primary_bases", side_effect=empty_stage("bases")),
            patch("pattern_engine.runner.detect_breakouts", side_effect=empty_stage("breakouts")),
            patch("pattern_engine.runner.detect_pullbacks", side_effect=empty_stage("pullbacks")),
            patch("pattern_engine.runner.detect_failures", side_effect=empty_stage("failures")),
        ):
            report = self._runner(FakeDataSource()).run_security(
                "GOOD", as_of, _VERSIONS, dry_run=True
            )

        self.assertEqual(PatternScanMode.DEBUG, report.mode)
        self.assertEqual(ImportStatus.COMPLETED, report.status)
        self.assertEqual(1, report.metrics["candidatesDetected"])
        self.assertEqual({}, self.patterns.instances)
        explanation = report.outcomes[0].candidates[0]
        self.assertEqual("synthetic", explanation["candidate"]["measurements"]["evidence"])
        self.assertIn("setup_contributions", explanation["candidate"]["measurements"]["scoring"])
        self.assertIn("contextComponents", explanation)
        self.assertEqual("EMITTED", explanation["ruleDecision"])
        self.assertEqual(
            ["supporting", "bases", "breakouts", "pullbacks", "failures"], calls
        )

    def test_one_bad_security_rolls_back_and_does_not_abort_universe(self):
        as_of = date(2026, 9, 5)

        def supporting(security, *args):
            return [_candidate(str(security["isin"]), as_of)]

        def bases(security, *args):
            if security["isin"] == "BAD":
                raise ValueError("malformed feature payload")
            return []

        patches = self._detector_patches(supporting)
        with patches[0], patch("pattern_engine.runner.detect_primary_bases", side_effect=bases), patches[2], patches[3], patches[4]:
            report = self._runner(FakeDataSource(("BAD", "GOOD"))).run_universe(
                as_of, _VERSIONS
            )

        self.assertEqual(ImportStatus.PARTIAL, report.status)
        self.assertEqual(1, report.metrics["securitiesCompleted"])
        self.assertEqual(1, report.metrics["securitiesFailed"])
        self.assertEqual(1, len(self.runs.failures))
        self.assertEqual("BAD", self.runs.failures[0]["isin"])
        self.assertEqual(
            ["GOOD"], [str(instance["isin"]) for instance in self.patterns.instances.values()]
        )

    def test_changed_mode_targets_only_affected_securities(self):
        as_of = date(2026, 9, 5)
        affected = [{"isin": "B", "latest_affected_date": as_of}]
        patches = self._detector_patches(lambda *args: [])
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            report = self._runner(FakeDataSource(("A", "B"), affected)).run_changed(
                "daily-run", _VERSIONS, dry_run=True
            )

        self.assertEqual(PatternScanMode.CHANGED, report.mode)
        self.assertEqual(1, report.metrics["targets"])
        self.assertEqual("B", report.outcomes[0].isin)
        self.assertEqual("daily-run", self.runs.created[0][2]["configuration"]["sourceRunId"])

    def test_completed_scan_expires_a_previously_active_condition_that_disappears(self):
        first_date = date(2026, 9, 5)
        first_patches = self._detector_patches(
            lambda security, *args: [_candidate(str(security["isin"]), first_date)]
        )
        with first_patches[0], first_patches[1], first_patches[2], first_patches[3], first_patches[4]:
            self._runner(FakeDataSource()).run_security("GOOD", first_date, _VERSIONS)

        second_patches = self._detector_patches(lambda *args: [])
        with second_patches[0], second_patches[1], second_patches[2], second_patches[3], second_patches[4]:
            report = self._runner(FakeDataSource()).run_security(
                "GOOD", first_date + timedelta(days=1), _VERSIONS
            )

        instance = next(iter(self.patterns.instances.values()))
        self.assertEqual(PatternState.EXPIRED.value, instance["state"])
        self.assertEqual(
            "CONDITION_NOT_PRESENT_IN_COMPLETED_SCAN",
            instance["measurements"]["expiration_reason"],
        )
        reconciliation = next(
            item for item in report.outcomes[0].stage_decisions
            if item["stage"] == "active_reconciliation"
        )
        self.assertEqual(1, reconciliation["expired"])

    def test_replay_uses_each_historical_session_without_live_writes(self):
        start = date(2026, 9, 4)
        data = FakeDataSource()

        def replay_bars(isin, from_date, to_date, adjustment_version):
            if from_date == start and to_date == start + timedelta(days=1):
                return [{"isin": isin, "trading_date": start}, {"isin": isin, "trading_date": start + timedelta(days=1)}]
            return FakeDataSource.load_adjusted_bars(data, isin, from_date, to_date, adjustment_version)

        data.load_adjusted_bars = replay_bars
        patches = self._detector_patches(lambda *args: [])
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            report = self._runner(data).replay(
                ("GOOD",), start, start + timedelta(days=1), _VERSIONS
            )

        self.assertEqual(PatternScanMode.REPLAY, report.mode)
        self.assertTrue(report.metrics["dryRun"])
        self.assertEqual(2, report.metrics["targets"])
        self.assertEqual({}, self.patterns.instances)

    def test_single_replay_target_does_not_read_live_patterns_and_keeps_snapshots(self):
        as_of = date(2026, 9, 5)
        self.patterns.instances["future-live-pattern"] = {
            "id": "future-live-pattern", "isin": "GOOD", "pattern_type": "BASE-VCP",
            "terminal_date": None, "last_updated_date": date(2026, 10, 1),
        }
        breakout_sources = []

        def capture_breakouts(*args):
            breakout_sources.extend(args[-1])
            return []

        with (
            patch("pattern_engine.runner.detect_supporting_patterns", return_value=[_candidate("GOOD", as_of)]),
            patch("pattern_engine.runner.detect_primary_bases", return_value=[]),
            patch("pattern_engine.runner.detect_breakouts", side_effect=capture_breakouts),
            patch("pattern_engine.runner.detect_pullbacks", return_value=[]),
            patch("pattern_engine.runner.detect_failures", return_value=[]),
        ):
            outcome = self._runner(FakeDataSource()).evaluate_replay_target(
                {"isin": "GOOD", "symbol": "GOOD"}, as_of, _VERSIONS
            )

        self.assertEqual([], breakout_sources)
        self.assertEqual("80", outcome.candidates[0]["featureSnapshot"]["relative_strength_percentile"])
        self.assertEqual("70", outcome.candidates[0]["marketSnapshot"]["market_regime_score"])


if __name__ == "__main__":
    unittest.main()
