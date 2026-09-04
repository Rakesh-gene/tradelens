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


class NseDataCollectorTestCase(unittest.TestCase):
    def test_download_equities_parses_and_persists_csv(self) -> None:
        repository = RecordingEquityRepository()
        collector = NseDataCollector(repository, FakeNseClient())

        self.assertEqual(collector.DownloadEquities(), 1)
        self.assertEqual(repository.equities[0]["symbol"], "20MICRONS")
        self.assertEqual(repository.equities[0]["listed_on"], date(2008, 10, 6))
        self.assertEqual(repository.equities[0]["market_lot"], 1)


if __name__ == "__main__":
    unittest.main()
