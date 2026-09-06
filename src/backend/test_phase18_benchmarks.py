import unittest

from benchmarks.phase18 import run_backfill_volume_benchmark


class Phase18BenchmarkHarnessTestCase(unittest.TestCase):
    def test_backfill_harness_is_batched_and_counts_every_row(self):
        result = run_backfill_volume_benchmark(25, 10)

        self.assertEqual(25, result["rows"])
        self.assertEqual(3, result["batches"])
        self.assertEqual("only one batch retained", result["memoryPolicy"])
        self.assertGreater(result["rowsPerSecond"], 0)


if __name__ == "__main__":
    unittest.main()
