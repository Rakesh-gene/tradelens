from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.research import BacktestService, calculate_outcomes, summarize_results
from repositories.research import InMemoryResearchRepository


_D = Decimal


def _bars(isin, start, count=61):
    return [
        {"isin": isin, "trading_date": start + timedelta(days=index), "high_price": _D("106") + index, "low_price": _D("96"), "close_price": _D("100") + index}
        for index in range(count)
    ]


class FakeEvaluator:
    def __init__(self):
        self.calls = []

    def evaluate(self, security, as_of_date, versions):
        self.calls.append((security["isin"], as_of_date))
        return [{
            "candidate": {
                "isin": security["isin"], "pattern_class": "BASE", "pattern_type": "BASE-VCP",
                "variant": "VCP-3C", "state": "TRIGGERED", "start_date": date(2025, 12, 1),
                "detected_date": as_of_date,
                "pivot_price": _D("100"), "setup_score": _D("88"),
                "quality_score": _D("90"), "maturity_score": _D("82"), "context_score": _D("76"),
                "supporting_pattern_identifiers": ["TREND-S2", "VOL-DRY"],
            },
            "featureSnapshot": {"relative_strength_6m": _D("85"), "volume_contraction_ratio": _D("0.55")},
            "marketSnapshot": {"market_regime_score": _D("70")},
            "sectorSnapshot": {"sector_strength_score": _D("75")},
            "ruleDecision": "EMITTED",
        }]


class HistoricalResearchTestCase(unittest.TestCase):
    def test_outcomes_cover_horizons_excursions_thresholds_and_completeness(self):
        start = date(2026, 1, 1)
        bars = _bars("A", start)
        bars[1].update(high_price=_D("106"), low_price=_D("94"), close_price=_D("105"))
        outcome = calculate_outcomes(_D("100"), bars)
        self.assertEqual(_D("5"), outcome["returns_by_horizon"]["5"])
        self.assertEqual(_D("11"), outcome["mfe_by_horizon"]["5"])
        self.assertEqual(_D("-6"), outcome["mae_by_horizon"]["5"])
        self.assertEqual(1, outcome["days_to_threshold"]["5"])
        self.assertFalse(outcome["hit_before_loss"]["plus5BeforeMinus5"])
        self.assertTrue(outcome["completeness"]["60"]["complete"])

    def test_missing_future_sessions_are_explicit_and_not_fabricated(self):
        outcome = calculate_outcomes(_D("100"), _bars("A", date(2026, 1, 1), 4))
        self.assertIsNone(outcome["returns_by_horizon"]["5"])
        self.assertFalse(outcome["completeness"]["5"]["complete"])
        self.assertEqual(3, outcome["completeness"]["5"]["availableSessions"])

    def test_replay_reconstructs_each_sessions_membership_and_deduplicates_entries(self):
        first, second = date(2026, 1, 1), date(2026, 1, 2)
        repository = InMemoryResearchRepository(
            sessions=[first, second],
            memberships={
                ("NIFTY500", first): [{"isin": "A", "sector_code": "TECH"}],
                ("NIFTY500", second): [{"isin": "A", "sector_code": "TECH"}, {"isin": "B", "sector_code": "TECH"}],
            },
            bars={"A": _bars("A", first, 65), "B": _bars("B", second, 65)},
        )
        evaluator = FakeEvaluator()
        service = BacktestService(repository, evaluator)
        response = service.start({
            "fromDate": first.isoformat(), "toDate": second.isoformat(),
            "universe": {"indexCode": "NIFTY500"},
            "versions": {"engine": "e1", "configuration": "c1", "feature": "f1", "adjustment": "a1"},
            "minimumSampleSize": 3,
            "filters": {"patternType": "BASE-VCP", "minRs6m": 80, "minMarketScore": 65, "minSectorScore": 70, "maxVolumeCompression": 0.60, "stage2": True, "volumeCompression": True},
        })
        run_id = response["run"]["runId"]
        self.assertEqual([("A", first), ("A", second), ("B", second)], evaluator.calls)
        self.assertEqual(2, response["run"]["entriesRecorded"])
        results = service.results(run_id, {"pageSize": ["10"]})
        self.assertEqual(2, results["summary"]["totalEntries"])
        probability = results["summary"]["hitBeforeLoss"]["plus5BeforeMinus5"]
        self.assertFalse(probability["adequateSample"])
        self.assertIsNone(probability["probabilityPct"])
        self.assertTrue(response["run"]["pointInTimePolicy"]["effectiveMembership"])

    def test_replay_can_target_one_explicit_stock(self):
        session = date(2026, 1, 1)
        repository = InMemoryResearchRepository(sessions=[session], bars={"INE002A01018": _bars("INE002A01018", session, 65)})
        evaluator = FakeEvaluator()
        response = BacktestService(repository, evaluator).start({
            "fromDate": session.isoformat(), "toDate": session.isoformat(),
            "universe": {"isin": "INE002A01018"},
            "versions": {"engine": "e1", "configuration": "c1", "feature": "f1", "adjustment": "a1"},
        })
        self.assertEqual([("INE002A01018", session)], evaluator.calls)
        self.assertEqual({"isin": "INE002A01018", "selectionPolicy": "explicit-security"}, response["run"]["universe"])

    def test_probability_is_shown_only_at_the_minimum_sample(self):
        rows = [{"returns_by_horizon": {"5": _D("2")}, "hit_before_loss": {"plus5BeforeMinus5": value}} for value in (True, False, True)]
        summary = summarize_results(rows, 3)
        self.assertTrue(summary["hitBeforeLoss"]["plus5BeforeMinus5"]["adequateSample"])
        self.assertEqual(_D("66.66666666666666666666666667"), summary["hitBeforeLoss"]["plus5BeforeMinus5"]["probabilityPct"])

    def test_invalid_request_requires_effective_dated_universe_and_versions(self):
        service = BacktestService(InMemoryResearchRepository(), FakeEvaluator())
        with self.assertRaisesRegex(ValueError, "indexCode"):
            service.start({"fromDate": "2026-01-01", "toDate": "2026-01-02", "versions": {"engine": "e", "configuration": "c", "feature": "f", "adjustment": "a"}})

    def test_failed_backtest_resumes_after_its_last_completed_session(self):
        first, second = date(2026, 1, 1), date(2026, 1, 2)
        repository = InMemoryResearchRepository(
            sessions=[first, second], memberships={("NIFTY500", second): []},
        )
        original = repository.create_run({
            "requested_from_date": first, "requested_to_date": second,
            "universe": {"indexCode": "NIFTY500"}, "filters": {},
            "engine_version": "e1", "configuration_version": "c1",
            "feature_version": "f1", "adjustment_version": "a1",
            "point_in_time_policy": {}, "minimum_sample_size": 30,
            "requested_by": None, "resumed_from_run_id": None,
        })
        repository.update_run(original, "FAILED", last_completed_session=first)
        resumed = BacktestService(repository, FakeEvaluator()).resume(original)
        self.assertEqual(second, resumed["run"]["fromDate"])
        self.assertEqual(original, resumed["run"]["resumedFromRunId"])


if __name__ == "__main__":
    unittest.main()
