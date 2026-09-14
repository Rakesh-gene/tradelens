from datetime import date, timedelta
from decimal import Decimal
import unittest

from operations.case_study_pipeline import CaseStudyPipeline
from pattern_engine.runner import PatternEngineVersions
from repositories.case_studies import InMemoryCaseStudyRepository


class CaseStudyPipelineTest(unittest.TestCase):
    def test_build_request_needs_only_stock_and_lookback(self):
        as_of = date(2026, 9, 12)
        repo = InMemoryCaseStudyRepository(
            bars={"INE002A01018": [{"trading_date": as_of}]},
            securities={"INE002A01018": {"isin": "INE002A01018", "symbol": "RELIANCE", "company_name": "Reliance Industries Limited"}},
        )

        class Research:
            def __init__(self): self.requests = []
            def start(self, payload, requested_by=None):
                self.requests.append(payload)
                return {"run": {"runId": "research", "status": "COMPLETED"}}

        research = Research()
        pipeline = CaseStudyPipeline(repo, research, versions=PatternEngineVersions("v2", "v2", "v1"), configuration_version="v2")
        pipeline._start_worker = pipeline._run_guarded
        response = pipeline.start({"isin": "ine002a01018", "lookback": "3m"})
        self.assertEqual("COMPLETED", response["run"]["status"])
        self.assertEqual("INE002A01018", response["run"]["stock"]["isin"])
        self.assertEqual("3M", response["run"]["lookback"])
        self.assertEqual(date(2026, 6, 12), response["run"]["fromDate"])
        self.assertEqual({"isin": "INE002A01018"}, research.requests[0]["universe"])

    def test_rejects_internal_build_inputs(self):
        pipeline = CaseStudyPipeline(InMemoryCaseStudyRepository())
        with self.assertRaisesRegex(ValueError, "Unknown case-study build field"):
            pipeline.start({"isin": "INE002A01018", "lookback": "1Y", "sourceBacktestRunId": "internal"})

    def test_neutral_context_signal_does_not_fail_directional_case_build(self):
        signal = date(2025, 1, 2)
        repo = InMemoryCaseStudyRepository(source_entries=[{
            "id": "neutral", "backtest_run_id": "research", "isin": "INE002A01018",
            "fingerprint_key": "neutral-fingerprint", "pattern_class": "COMPRESSION",
            "pattern_type": "COMP-NR7", "state": "TRIGGERED", "entry_date": signal,
            "candidate_fingerprint": {"candidate": {"direction": "NEUTRAL"}},
        }])
        pipeline = CaseStudyPipeline(repo)
        run_id = repo.create_run({"requested_from_date": signal, "requested_to_date": signal, "universe": {"isin": "INE002A01018"}, "source_backtest_run_id": "research", "requested_pattern_types": [], "requested_timeframes": ["1D"], "engine_version": "e", "configuration_version": "c", "feature_version": "f", "adjustment_version": "a", "trade_policy_version": "swing-trade-v1", "selection_policy_version": "case-study-selection-v1", "trade_policy_inputs": {}})
        pipeline._run(run_id)
        self.assertEqual("COMPLETED", repo.get_run(run_id)["status"])
        self.assertEqual([], repo.cases)

    def test_builds_a_durable_case_from_explicit_replay_source(self):
        signal = date(2025, 1, 2)
        bars = [{"trading_date": signal + timedelta(days=offset), "open_price": Decimal("100"), "high_price": Decimal("111" if offset == 2 else "101"), "low_price": Decimal("99"), "close_price": Decimal("110" if offset == 2 else "100")} for offset in range(1, 23)]
        repo = InMemoryCaseStudyRepository(source_entries=[{"id": "entry", "backtest_run_id": "research", "isin": "INE002A01018", "fingerprint_key": "fingerprint", "pattern_class": "BASE", "pattern_type": "BASE-VCP", "state": "TRIGGERED", "entry_date": signal, "candidate_fingerprint": {"candidate": {"invalidation_price": Decimal("95"), "pivot_price": Decimal("100")}}}], bars={"INE002A01018": bars})
        pipeline = CaseStudyPipeline(repo)
        run_id = repo.create_run({"requested_from_date": signal, "requested_to_date": signal, "universe": {}, "source_backtest_run_id": "research", "requested_pattern_types": [], "requested_timeframes": ["1D"], "engine_version": "e", "configuration_version": "c", "feature_version": "f", "adjustment_version": "a", "trade_policy_version": "swing-trade-v1", "selection_policy_version": "case-study-selection-v1", "trade_policy_inputs": {}})
        pipeline._run(run_id)
        self.assertEqual(1, len(repo.cases))
        self.assertEqual("TARGET_HIT", repo.cases[0]["exit_reason"])
