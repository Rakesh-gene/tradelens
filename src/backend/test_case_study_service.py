from datetime import date
from decimal import Decimal
import unittest

from pattern_engine.case_study_service import CaseStudyService
from repositories.case_studies import InMemoryCaseStudyRepository


class CaseStudyServiceTest(unittest.TestCase):
    def setUp(self):
        self.service = CaseStudyService(InMemoryCaseStudyRepository([{
            "id": "00000000-0000-0000-0000-000000000001", "isin": "INE002A01018", "historical_symbol": "RELIANCE", "pattern_type": "BASE-VCP", "timeframe": "DAILY", "direction": "BULLISH", "detection_date": date(2025, 1, 2), "entry_date": date(2025, 1, 3), "entry_price": Decimal("100"), "exit_price": Decimal("110"), "exit_reason": "TARGET_HIT", "net_pnl": Decimal("2000"), "net_return_pct": Decimal("10"), "net_r_multiple": Decimal("2"), "completeness": {}, "lineage": {"engineVersion": "e1", "configurationVersion": "c1"}, "measurements": {}, "supporting_evidence": {}, "context": {}, "ambiguity": {}, "quantity": 200,
        }]))
    def test_catalog_filters_and_exposes_market_lineage(self):
        payload = self.service.catalog({"patternType": ["BASE-VCP"]})
        self.assertEqual("RELIANCE", payload["items"][0]["symbol"])
        self.assertEqual("e1", payload["engineVersion"])
    def test_detail_and_chart_are_stable_server_contracts(self):
        identifier = "00000000-0000-0000-0000-000000000001"
        self.assertEqual(identifier, self.service.detail(identifier)["caseStudy"]["caseStudyId"])
        self.assertEqual(identifier, self.service.chart(identifier, {})["caseStudyId"])
    def test_unknown_case_is_not_fabricated(self):
        with self.assertRaises(ValueError): self.service.detail("unknown")
    def test_admin_can_review_and_publish_a_pending_case(self):
        pending = self.service.review_queue({"status": ["PENDING"]})
        self.assertEqual(1, len(pending["items"]))
        identifier = pending["items"][0]["caseStudyId"]
        reviewed = self.service.review(identifier, {"status": "REVIEWED"})
        self.assertEqual("REVIEWED", reviewed["caseStudy"]["reviewStatus"])
        self.assertEqual([], self.service.review_queue({"status": ["PENDING"]})["items"])

    def test_admin_can_delete_a_case(self):
        identifier = "00000000-0000-0000-0000-000000000001"
        self.assertEqual(identifier, self.service.delete(identifier)["deletedCaseStudyId"])
        with self.assertRaises(LookupError):
            self.service.detail(identifier)

    def test_non_setup_pattern_cannot_be_published_or_enter_catalog(self):
        repository = InMemoryCaseStudyRepository([{
            "id": "00000000-0000-0000-0000-000000000002", "isin": "INE002A01018",
            "pattern_type": "REV-DBOT", "timeframe": "1D", "direction": "BULLISH",
            "detection_date": date(2025, 1, 2), "review_status": "PENDING",
            "lineage": {}, "measurements": {}, "supporting_evidence": {}, "context": {},
        }])
        service = CaseStudyService(repository)
        identifier = "00000000-0000-0000-0000-000000000002"
        with self.assertRaisesRegex(ValueError, "Setups page"):
            service.review(identifier, {"status": "REVIEWED"})
        repository.set_review_status(identifier, "REVIEWED")
        self.assertEqual([], service.catalog({})["items"])
