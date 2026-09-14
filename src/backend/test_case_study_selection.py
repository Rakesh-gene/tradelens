from datetime import date
from decimal import Decimal
import unittest

from pattern_engine.case_study_selection import select_representative_cases


def case(identifier, forward_return, **extra):
    return {"id": identifier, "isin": "INE" + identifier, "entry_date": date(2026, 1, int(identifier)), "replay_fingerprint": identifier, "pattern_type": "BASE-VCP", "variant": "VCP-3C", "timeframe": "DAILY", "direction": "BULLISH", "market_regime": "STRONG", "sector_context": "STRONG", "forward_return_pct": None if forward_return is None else Decimal(forward_return), **extra}


class CaseStudySelectionTest(unittest.TestCase):
    def test_selection_is_deterministic_and_retains_forward_range_and_incomplete_cases(self):
        rows = [case("3", "30"), case("1", "-20"), case("2", None)]
        selected = select_representative_cases(reversed(rows))
        self.assertEqual({"1", "2", "3"}, {row["id"] for row in selected})
        self.assertEqual([row["id"] for row in selected], [row["id"] for row in select_representative_cases(rows)])
        self.assertEqual("case-study-selection-v2", selected[0]["selection_policy_version"])
        self.assertEqual(3, len(selected))
