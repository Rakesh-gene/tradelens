from decimal import Decimal
import unittest

from pattern_engine.decision_intelligence import build_decision


def setup(state="READY", **overrides):
    value = {
        "state": state, "variant": "VCP-2C", "patternType": "BASE-VCP",
        "setupScore": Decimal("88"), "qualityScore": Decimal("90"),
        "maturityScore": Decimal("84"), "contextScore": Decimal("76"),
        "liquidityScore": Decimal("92"), "pivotPrice": Decimal("100"),
        "distanceToPivotPct": Decimal("-2"), "evidenceCount": 3,
        "bestFit": {"tier": "STRONG"},
    }
    value.update(overrides)
    return value


class DecisionIntelligenceTestCase(unittest.TestCase):
    def test_ready_vcp_explains_action_levels_and_plain_language(self):
        decision = build_decision(
            {"relative_strength_percentile": Decimal("94"), "support_price": Decimal("92"), "invalidation_price": Decimal("88")},
            setup(),
        )
        self.assertEqual("WAIT_FOR_BREAKOUT", decision["action"])
        self.assertEqual("Ready — high-quality two-contraction VCP", decision["headline"])
        self.assertEqual("HIGH", decision["confidenceBand"])
        self.assertEqual(Decimal("12.00"), decision["levels"]["riskFromTriggerPct"])
        self.assertIn("Relative strength", " ".join(decision["strengths"]))
        self.assertEqual([], decision["missingEvidence"])

    def test_each_lifecycle_state_has_an_explicit_operating_action(self):
        expected = {
            "DETECTED": "OBSERVE", "FORMING": "WATCH", "MATURE": "PREPARE",
            "READY": "WAIT_FOR_BREAKOUT", "TRIGGERED": "WAIT_FOR_CONFIRMATION",
            "CONFIRMED": "ENTRY_CONFIRMED", "FAILED": "EXIT_OR_AVOID",
            "INVALIDATED": "EXIT_OR_AVOID", "EXPIRED": "IGNORE",
        }
        for state, action in expected.items():
            with self.subTest(state=state):
                decision = build_decision({"invalidation_price": 88}, setup(state))
                self.assertEqual(action, decision["action"])
        self.assertEqual("HOLD_WHILE_VALID", build_decision({"invalidation_price": 88}, setup("CONFIRMED"))["holdingAction"])

    def test_missing_evidence_reduces_confidence_and_is_disclosed(self):
        decision = build_decision(
            {},
            setup(qualityScore=None, contextScore=None, liquidityScore=None, pivotPrice=None),
        )
        self.assertLess(decision["confidenceScore"], Decimal("80"))
        self.assertIn("pattern quality", decision["missingEvidence"])
        self.assertIn("trigger price", decision["missingEvidence"])
        self.assertEqual("Evidence alignment and completeness, not historical probability.", decision["confidenceMeaning"])


if __name__ == "__main__":
    unittest.main()
