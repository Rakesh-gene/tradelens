"""Opt-in live-source contract tests; excluded from deterministic CI by default."""

from datetime import date
import os
import unittest

from data_pipeline.nse_api import NseApiClient


@unittest.skipUnless(
    os.getenv("TRADELENS_RUN_LIVE_NSE_TESTS") == "1",
    "set TRADELENS_RUN_LIVE_NSE_TESTS=1 to contact NSE",
)
class LiveNseContractTestCase(unittest.TestCase):
    def test_reliance_history_and_known_2024_actions_match_the_parser_contract(self):
        client = NseApiClient(max_requests_per_second=1)

        history = client.fetch_equity_history(
            "RELIANCE", date(2024, 1, 1), date(2024, 1, 5)
        )
        actions = client.fetch_corporate_actions(
            "RELIANCE", date(2024, 7, 1), date(2024, 11, 30)
        )

        self.assertEqual(5, len(history))
        self.assertTrue(all(row.symbol == "RELIANCE" for row in history))
        self.assertEqual(date(2024, 1, 1), history[0].trading_date)
        self.assertEqual(date(2024, 1, 5), history[-1].trading_date)
        self.assertTrue(
            any(action.action_type == "BONUS" and action.ex_date == date(2024, 10, 28) for action in actions)
        )
        self.assertEqual(client.metrics["requestAttempts"], client.metrics["successfulRequests"])


if __name__ == "__main__":
    unittest.main()
