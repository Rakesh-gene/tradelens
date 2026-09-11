from decimal import Decimal
import unittest

from pattern_engine.scoring import available_weighted_score


class AvailableWeightedScoreTestCase(unittest.TestCase):
    def test_missing_context_is_excluded_instead_of_counted_as_zero(self):
        result = available_weighted_score(
            {"market": Decimal("80"), "sector": None},
            {"market": Decimal("60"), "sector": Decimal("40")},
        )

        self.assertEqual(Decimal("80"), result.total)
        self.assertEqual(Decimal("0"), result.contributions["sector"])

    def test_all_missing_context_remains_zero(self):
        result = available_weighted_score(
            {"market": None, "sector": None},
            {"market": Decimal("60"), "sector": Decimal("40")},
        )

        self.assertEqual(Decimal("0"), result.total)


if __name__ == "__main__":
    unittest.main()
