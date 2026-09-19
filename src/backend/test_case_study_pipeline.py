from datetime import date, timedelta
from decimal import Decimal
import unittest

from operations.case_study_pipeline import CaseStudyPipeline
from pattern_engine.runner import PatternEngineVersions
from pattern_engine.enums import SETUP_PATTERN_TYPES
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
            def start(self, payload, requested_by=None, *, on_run_created=None):
                self.requests.append(payload)
                if on_run_created: on_run_created("research")
                return {"run": {"runId": "research", "status": "COMPLETED"}}
            def get_run(self, run_id):
                return {"run": {"status": "COMPLETED", "sessionsProcessed": 1, "entriesRecorded": 0}}

        research = Research()
        pipeline = CaseStudyPipeline(repo, research, versions=PatternEngineVersions("v2", "v2", "v1"), configuration_version="v2")
        pipeline._start_worker = pipeline._run_guarded
        response = pipeline.start({"isin": "ine002a01018", "lookback": "3m"})
        self.assertEqual("COMPLETED", response["run"]["status"])
        self.assertEqual("INE002A01018", response["run"]["stock"]["isin"])
        self.assertEqual("3M", response["run"]["lookback"])
        self.assertEqual(date(2026, 6, 12), response["run"]["fromDate"])
        self.assertEqual({"isin": "INE002A01018"}, research.requests[0]["universe"])
        self.assertEqual(list(SETUP_PATTERN_TYPES), repo.get_run(response["run"]["runId"])["requested_pattern_types"])

    def test_rejects_internal_build_inputs(self):
        pipeline = CaseStudyPipeline(InMemoryCaseStudyRepository())
        with self.assertRaisesRegex(ValueError, "Unknown case-study build field"):
            pipeline.start({"isin": "INE002A01018", "lookback": "1Y", "sourceBacktestRunId": "internal"})

    def test_neutral_setup_builds_a_long_stock_case(self):
        signal = date(2025, 1, 2)
        bars = [{"trading_date": signal + timedelta(days=offset), "open_price": Decimal("100"), "high_price": Decimal("102"), "low_price": Decimal("98"), "close_price": Decimal("101")} for offset in range(1, 25)]
        repo = InMemoryCaseStudyRepository(source_entries=[{
            "id": "neutral", "backtest_run_id": "research", "isin": "INE002A01018",
            "fingerprint_key": "neutral-fingerprint", "pattern_class": "COMPRESSION",
            "pattern_type": "COMP-NR7", "state": "TRIGGERED", "entry_date": signal,
            "candidate_fingerprint": {"candidate": {"direction": "NEUTRAL", "invalidation_price": Decimal("95"), "pivot_price": Decimal("100")}},
        }], bars={"INE002A01018": bars})
        pipeline = CaseStudyPipeline(repo)
        run_id = repo.create_run({"requested_from_date": signal, "requested_to_date": signal, "universe": {"isin": "INE002A01018"}, "source_backtest_run_id": "research", "requested_pattern_types": [], "requested_timeframes": ["1D"], "engine_version": "e", "configuration_version": "c", "feature_version": "f", "adjustment_version": "a", "trade_policy_version": "swing-trade-v1", "selection_policy_version": "case-study-selection-v1", "trade_policy_inputs": {}})
        pipeline._run(run_id)
        self.assertEqual("COMPLETED", repo.get_run(run_id)["status"])
        self.assertEqual(1, len(repo.cases))
        self.assertEqual("NEUTRAL", repo.cases[0]["direction"])
        self.assertEqual("BULLISH", repo.cases[0]["trade"]["direction"])

    def test_builds_a_durable_case_from_explicit_replay_source(self):
        signal = date(2025, 1, 2)
        bars = [{"trading_date": signal + timedelta(days=offset), "open_price": Decimal("100"), "high_price": Decimal("111" if offset == 2 else "101"), "low_price": Decimal("99"), "close_price": Decimal("110" if offset == 2 else "100")} for offset in range(1, 23)]
        repo = InMemoryCaseStudyRepository(source_entries=[{"id": "entry", "backtest_run_id": "research", "isin": "INE002A01018", "fingerprint_key": "fingerprint", "pattern_class": "BASE", "pattern_type": "BASE-VCP", "state": "TRIGGERED", "entry_date": signal, "candidate_fingerprint": {"candidate": {"invalidation_price": Decimal("95"), "pivot_price": Decimal("100")}}}], bars={"INE002A01018": bars})
        pipeline = CaseStudyPipeline(repo)
        run_id = repo.create_run({"requested_from_date": signal, "requested_to_date": signal, "universe": {}, "source_backtest_run_id": "research", "requested_pattern_types": [], "requested_timeframes": ["1D"], "engine_version": "e", "configuration_version": "c", "feature_version": "f", "adjustment_version": "a", "trade_policy_version": "swing-trade-v1", "selection_policy_version": "case-study-selection-v1", "trade_policy_inputs": {}})
        pipeline._run(run_id)
        self.assertEqual(1, len(repo.cases))
        self.assertEqual("TARGET_HIT", repo.cases[0]["exit_reason"])

    def test_excludes_patterns_not_available_in_the_setups_dropdown(self):
        signal = date(2025, 1, 2)
        repo = InMemoryCaseStudyRepository(source_entries=[{
            "id": "reversal", "backtest_run_id": "research", "isin": "INE002A01018",
            "fingerprint_key": "reversal-fingerprint", "pattern_class": "REVERSAL",
            "pattern_type": "REV-DBOT", "state": "TRIGGERED", "entry_date": signal,
            "candidate_fingerprint": {"candidate": {"direction": "BULLISH", "timeframe": "1D"}},
        }])
        pipeline = CaseStudyPipeline(repo)
        run_id = repo.create_run({"requested_from_date": signal, "requested_to_date": signal, "universe": {"isin": "INE002A01018"}, "source_backtest_run_id": "research", "requested_pattern_types": [], "requested_timeframes": ["1D"], "engine_version": "e", "configuration_version": "c", "feature_version": "f", "adjustment_version": "a", "trade_policy_version": "swing-trade-v1", "selection_policy_version": "case-study-selection-v2", "trade_policy_inputs": {}})
        pipeline._run(run_id)
        self.assertEqual([], repo.cases)

    def test_run_status_exposes_source_replay_progress(self):
        class Research:
            def get_run(self, run_id):
                return {"run": {"status": "RUNNING", "sessionsProcessed": 45, "entriesRecorded": 3, "lastCompletedSession": date(2025, 2, 15)}}

        repo = InMemoryCaseStudyRepository()
        pipeline = CaseStudyPipeline(repo, Research())
        run_id = repo.create_run({"requested_from_date": date(2025, 1, 1), "requested_to_date": date(2025, 4, 1), "universe": {"symbol": "RELIANCE"}, "source_backtest_run_id": "research", "trade_policy_version": "swing-trade-v1", "selection_policy_version": "case-study-selection-v2"})
        repo.update_run(run_id, status="RUNNING")
        run = pipeline.get(run_id)["run"]
        self.assertEqual("REPLAYING_HISTORY", run["stage"])
        self.assertGreater(run["progressPct"], 0)
        self.assertEqual(45, run["sessionsProcessed"])
        self.assertEqual(3, run["sourceEntriesRecorded"])

    def test_resume_restarts_an_incomplete_source_replay(self):
        class Research:
            def start(self, payload, requested_by=None, *, on_run_created=None):
                on_run_created("replacement")
                return {"run": {"runId": "replacement", "status": "COMPLETED"}}
            def get_run(self, run_id):
                return {"run": {"status": "FAILED"}}

        repo = InMemoryCaseStudyRepository()
        pipeline = CaseStudyPipeline(repo, Research())
        run_id = repo.create_run({"requested_from_date": date(2025, 1, 1), "requested_to_date": date(2025, 4, 1), "universe": {"isin": "INE002A01018"}, "source_backtest_run_id": "interrupted", "engine_version": "e", "configuration_version": "c", "feature_version": "f", "adjustment_version": "a"})
        pipeline._prepare_source(run_id)
        self.assertEqual("replacement", repo.get_run(run_id)["source_backtest_run_id"])

    def test_latest_run_is_scoped_to_the_requesting_admin(self):
        repo = InMemoryCaseStudyRepository()
        pipeline = CaseStudyPipeline(repo)
        values = {"requested_from_date": date(2025, 1, 1), "requested_to_date": date(2025, 4, 1), "universe": {"symbol": "RELIANCE"}, "source_backtest_run_id": None, "trade_policy_version": "swing-trade-v1", "selection_policy_version": "case-study-selection-v2"}
        first = repo.create_run({**values, "requested_by": "admin-1"})
        repo.create_run({**values, "requested_by": "admin-2"})
        self.assertEqual(first, pipeline.latest("admin-1")["run"]["runId"])
        self.assertIsNone(pipeline.latest("admin-3")["run"])
