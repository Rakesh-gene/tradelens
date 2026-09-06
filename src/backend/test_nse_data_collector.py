from datetime import date
import unittest

from data_pipeline.nse_data_collector import NseDataCollector


class FakeNseClient:
    def download_equities_csv(self) -> bytes:
        return (
            b"SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
            b"20MICRONS,20 Microns Limited,EQ,06-OCT-2008,5,1,INE144J01027,5\n"
        )


class RecordingEquityRepository:
    def __init__(self) -> None:
        self.equities: list[dict[str, object]] = []

    def upsert_equities(self, equities: list[dict[str, object]]) -> int:
        self.equities = equities
        return len(equities)


class RecordingRunRepository:
    def __init__(self): self.created = []; self.updated = []
    def create_import_run(self, job_type, initiated_by, **values): self.created.append((job_type, initiated_by)); return "run-1"
    def update_import_run(self, run_id, status, **values): self.updated.append((run_id, status, values))


class NseDataCollectorTestCase(unittest.TestCase):
    def test_download_equities_parses_and_persists_csv(self) -> None:
        repository = RecordingEquityRepository()
        collector = NseDataCollector(repository, FakeNseClient())

        self.assertEqual(collector.DownloadEquities(), 1)
        self.assertEqual(repository.equities[0]["symbol"], "20MICRONS")
        self.assertEqual(repository.equities[0]["listed_on"], date(2008, 10, 6))
        self.assertEqual(repository.equities[0]["market_lot"], 1)

    def test_equity_master_import_records_observable_run_metrics(self) -> None:
        runs = RecordingRunRepository()
        collector = NseDataCollector(RecordingEquityRepository(), FakeNseClient(), run_repository=runs)
        collector.download_equities()
        self.assertEqual("EQUITY_MASTER", runs.created[0][0].value)
        self.assertEqual("COMPLETED", runs.updated[-1][1].value)
        self.assertEqual(1, runs.updated[-1][2]["rows_downloaded"])
        self.assertIn("duration_ms", runs.updated[-1][2])


if __name__ == "__main__":
    unittest.main()
