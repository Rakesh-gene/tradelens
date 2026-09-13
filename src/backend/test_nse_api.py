from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from threading import Barrier, Lock
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from data_pipeline.normalization import (
    NseDataValidationError,
    parse_corporate_actions_response,
    parse_equity_classification_response,
    parse_equity_history_response,
    raw_bar_record,
)
from data_pipeline.nse_api import NseApiClient, NseResponseError


FIXTURE_DIRECTORY = Path(__file__).resolve().parent / "fixtures" / "nse"


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json", status: int = 200) -> None:
        self._body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class QueueOpener:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self._responses = deque(responses)
        self.requests = []

    def open(self, request, timeout: float):
        self.requests.append(request)
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


class ConcurrentOpener:
    def __init__(self) -> None:
        self._barrier = Barrier(2)
        self._lock = Lock()
        self._active = 0
        self.max_active = 0

    def open(self, request, timeout: float):
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            self._barrier.wait(timeout=2)
            return FakeResponse(_fixture("equity_history_empty.json"))
        finally:
            with self._lock:
                self._active -= 1


class OpenerFactoryTracker:
    def __init__(self) -> None:
        self._barrier = Barrier(2)
        self._lock = Lock()
        self.created = []
        self.active = 0
        self.max_active = 0

    def create(self):
        opener = PerThreadOpener(self)
        with self._lock:
            self.created.append(opener)
        return opener


class IndexFallbackOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if "nseindia.com" in request.full_url:
            raise HTTPError(request.full_url, 503, "unavailable", {}, None)
        return FakeResponse(json.dumps([{
            "INDEX_NAME": "NIFTY 500", "HistoricalDate": "04-Sep-2026",
            "OPEN": "100", "HIGH": "105", "LOW": "99", "CLOSE": "104",
        }]).encode())


class PerThreadOpener:
    def __init__(self, tracker: OpenerFactoryTracker) -> None:
        self._tracker = tracker

    def open(self, request, timeout: float):
        with self._tracker._lock:
            self._tracker.active += 1
            self._tracker.max_active = max(
                self._tracker.max_active, self._tracker.active
            )
        try:
            self._tracker._barrier.wait(timeout=2)
            return FakeResponse(_fixture("equity_history_empty.json"))
        finally:
            with self._tracker._lock:
                self._tracker.active -= 1


def _fixture(name: str) -> bytes:
    return (FIXTURE_DIRECTORY / name).read_bytes()


class NseApiClientTestCase(unittest.TestCase):
    def test_equity_trading_day_uses_cash_market_holidays_and_caches_the_year(self) -> None:
        opener = QueueOpener([FakeResponse(json.dumps({
            "CM": [{"tradingDate": "26-Jan-2026"}], "FO": [],
        }).encode())])
        client = NseApiClient(opener=opener, sleeper=lambda _: None)

        self.assertFalse(client.is_equity_trading_day(date(2026, 1, 26)))
        self.assertTrue(client.is_equity_trading_day(date(2026, 1, 27)))
        self.assertFalse(client.is_equity_trading_day(date(2026, 1, 25)))
        self.assertEqual(1, len(opener.requests))
        self.assertEqual("/api/holiday-master", urlparse(opener.requests[0].full_url).path)

    def test_fetch_equity_classification_uses_quote_endpoint_and_validates_identity(self) -> None:
        opener = QueueOpener([FakeResponse(_fixture("equity_classification_valid.json"))])
        client = NseApiClient(opener=opener, sleeper=lambda _: None)

        record = client.fetch_equity_classification(" reliance ", "INE002A01018")

        self.assertEqual("Oil Gas & Consumable Fuels", record.sector)
        self.assertEqual("Refineries & Marketing", record.basic_industry)
        self.assertEqual("/api/NextApi/apiClient/GetQuoteApi", urlparse(opener.requests[0].full_url).path)
        query = parse_qs(urlparse(opener.requests[0].full_url).query)
        self.assertEqual(["getSymbolData"], query["functionName"])

    def test_equity_classification_rejects_an_isin_mismatch(self) -> None:
        payload = json.loads(_fixture("equity_classification_valid.json"))
        with self.assertRaisesRegex(NseDataValidationError, "stable security ISIN"):
            parse_equity_classification_response(payload, "RELIANCE", "INE999A01010")

    def test_index_history_falls_back_to_official_nse_indices_source(self) -> None:
        opener = IndexFallbackOpener()
        client = NseApiClient(
            opener=opener, max_retries=0,
            max_requests_per_second=1000, sleeper=lambda _: None,
        )

        records = client.fetch_index_history(
            "NIFTY 500", date(2026, 9, 1), date(2026, 9, 4)
        )

        self.assertEqual(1, len(records))
        self.assertEqual(Decimal("104"), records[0].close_price)
        fallback = opener.requests[-1]
        self.assertEqual("POST", fallback.get_method())
        self.assertIn(b"NIFTY 500", fallback.data)

    def test_each_worker_thread_uses_an_independent_http_session(self) -> None:
        tracker = OpenerFactoryTracker()
        client = NseApiClient(
            opener_factory=tracker.create,
            max_requests_per_second=1000,
            sleeper=lambda _: None,
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    client.fetch_equity_history,
                    symbol,
                    date(2026, 9, 4),
                    date(2026, 9, 4),
                )
                for symbol in ("EXAMPLE", "OTHER")
            ]
            self.assertEqual([[], []], [future.result() for future in futures])

        self.assertEqual(2, len(tracker.created))
        self.assertEqual(2, tracker.max_active)

    def test_timeout_recycles_worker_session_before_retry(self) -> None:
        openers = deque([
            QueueOpener([TimeoutError("stale session")]),
            QueueOpener([FakeResponse(_fixture("equity_history_empty.json"))]),
        ])
        client = NseApiClient(
            opener_factory=openers.popleft,
            max_retries=1,
            sleeper=lambda _: None,
        )

        records = client.fetch_equity_history(
            "EXAMPLE", date(2026, 9, 4), date(2026, 9, 4)
        )

        self.assertEqual([], records)
        self.assertEqual(1, client.metrics["sessionResets"])
        self.assertEqual(2, client.metrics["requestAttempts"])

    def test_repeated_transport_failures_open_shared_cooldown_gate(self) -> None:
        sleeps = []
        openers = deque([
            QueueOpener([TimeoutError("first")]),
            QueueOpener([TimeoutError("second")]),
            QueueOpener([FakeResponse(_fixture("equity_history_empty.json"))]),
        ])
        client = NseApiClient(
            opener_factory=openers.popleft,
            max_retries=2,
            max_requests_per_second=1000,
            circuit_breaker_threshold=2,
            circuit_breaker_cooldown_seconds=7,
            sleeper=sleeps.append,
            random_value=lambda: 0.0,
        )

        self.assertEqual(
            [],
            client.fetch_equity_history(
                "EXAMPLE", date(2026, 9, 4), date(2026, 9, 4)
            ),
        )
        self.assertEqual(1, client.metrics["circuitBreakerTrips"])
        self.assertTrue(any(delay >= 6.9 for delay in sleeps))

    def test_slow_responses_do_not_hold_the_shared_request_slot_lock(self) -> None:
        opener = ConcurrentOpener()
        client = NseApiClient(
            opener=opener, max_requests_per_second=1000,
            sleeper=lambda _: None,
        )

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    client.fetch_equity_history,
                    symbol,
                    date(2026, 9, 4),
                    date(2026, 9, 4),
                )
                for symbol in ("EXAMPLE", "OTHER")
            ]
            self.assertEqual([[], []], [future.result() for future in futures])

        self.assertEqual(2, opener.max_active)

    def test_fetch_equity_history_chunks_range_and_returns_validated_dtos(self) -> None:
        opener = QueueOpener([
            FakeResponse(_fixture("equity_history_empty.json")),
            FakeResponse(_fixture("equity_history_valid.json")),
        ])
        client = NseApiClient(opener=opener, max_history_days=2, sleeper=lambda _: None)

        records = client.fetch_equity_history(" example ", date(2026, 9, 1), date(2026, 9, 4))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].symbol, "EXAMPLE")
        self.assertEqual(records[0].trading_date, date(2026, 9, 4))
        self.assertEqual(records[0].close_price, Decimal("1010.00"))
        self.assertEqual(records[0].volume, 1234567)
        self.assertEqual(records[0].deliverable_quantity, 500000)
        self.assertEqual(records[0].delivery_percentage, Decimal("40.50"))

        first_query = parse_qs(urlparse(opener.requests[0].full_url).query)
        second_query = parse_qs(urlparse(opener.requests[1].full_url).query)
        self.assertEqual(
            "/api/NextApi/apiClient/GetQuoteApi",
            urlparse(opener.requests[0].full_url).path,
        )
        self.assertEqual(first_query["functionName"], ["getHistoricalTradeData"])
        self.assertEqual(first_query["fromDate"], ["01-09-2026"])
        self.assertEqual(second_query["toDate"], ["04-09-2026"])
        self.assertEqual(opener.requests[0].get_header("Referer"), NseApiClient.HOME_URL)

    def test_history_keeps_nse_reported_previous_close(self) -> None:
        payload = {"data": [{
            "chSymbol": "EXAMPLE", "chSeries": "EQ", "mtimestamp": "04-Sep-2026",
            "chOpeningPrice": 51, "chTradeHighPrice": 52, "chTradeLowPrice": 49,
            "chClosingPrice": 50, "chPreviousClsPrice": 50,
            "chTotTradedQty": 1000,
        }]}

        record = parse_equity_history_response(payload, "EXAMPLE")[0]

        self.assertEqual(record.previous_close_price, Decimal("50"))

    def test_history_accepts_current_nested_nse_record_envelope(self) -> None:
        row = {
            "chSymbol": "EXAMPLE", "chSeries": "EQ", "mtimestamp": "04-Sep-2026",
            "chOpeningPrice": 51, "chTradeHighPrice": 52, "chTradeLowPrice": 49,
            "chClosingPrice": 50, "chTotTradedQty": 1000,
        }

        records = parse_equity_history_response({"data": {"rows": [row]}}, "EXAMPLE")

        self.assertEqual(1, len(records))
        self.assertEqual(date(2026, 9, 4), records[0].trading_date)

    def test_empty_nested_nse_record_envelope_is_not_an_error(self) -> None:
        self.assertEqual([], parse_equity_history_response({"data": {}}, "EXAMPLE"))

    def test_empty_history_response_returns_no_records(self) -> None:
        client = NseApiClient(opener=QueueOpener([FakeResponse(_fixture("equity_history_empty.json"))]))

        self.assertEqual(client.fetch_equity_history("EXAMPLE", date(2026, 9, 4), date(2026, 9, 4)), [])

    def test_retries_rate_limit_with_exponential_backoff(self) -> None:
        sleeps: list[float] = []
        opener = QueueOpener([
            HTTPError("https://nse.test", 429, "rate limited", {}, None),
            FakeResponse(_fixture("equity_history_empty.json")),
        ])
        client = NseApiClient(
            opener=opener,
            max_retries=1,
            sleeper=sleeps.append,
            random_value=lambda: 0.0,
        )

        self.assertEqual(client.fetch_equity_history("EXAMPLE", date(2026, 9, 4), date(2026, 9, 4)), [])
        self.assertEqual(len(opener.requests), 2)
        self.assertIn(0.25, sleeps)
        self.assertEqual(2, client.metrics["requestAttempts"])
        self.assertEqual(1, client.metrics["rateLimitedRequests"])
        self.assertEqual(1, client.metrics["successfulRequests"])

    def test_retries_transient_not_found_from_nse_edge(self) -> None:
        opener = QueueOpener([
            HTTPError("https://nse.test", 404, "temporary edge miss", {}, None),
            FakeResponse(b"<html>NSE</html>", "text/html"),
            FakeResponse(_fixture("equity_history_valid.json")),
        ])
        client = NseApiClient(
            opener=opener, max_retries=1, sleeper=lambda _: None,
            random_value=lambda: 0.0,
        )

        records = client.fetch_equity_history(
            "EXAMPLE", date(2026, 9, 4), date(2026, 9, 4)
        )

        self.assertEqual(1, len(records))
        self.assertEqual(2, client.metrics["requestAttempts"])
        self.assertEqual(opener.requests[1].full_url, NseApiClient.HOME_URL)

    def test_403_primes_session_before_retrying(self) -> None:
        opener = QueueOpener([
            HTTPError("https://nse.test", 403, "denied", {}, None),
            FakeResponse(b"<html>NSE</html>", "text/html"),
            FakeResponse(_fixture("equity_history_empty.json")),
        ])
        client = NseApiClient(opener=opener, max_retries=1, sleeper=lambda _: None)

        self.assertEqual(client.fetch_equity_history("EXAMPLE", date(2026, 9, 4), date(2026, 9, 4)), [])
        self.assertEqual(opener.requests[1].full_url, NseApiClient.HOME_URL)

    def test_404_primes_session_before_retrying(self) -> None:
        opener = QueueOpener([
            HTTPError("https://nse.test", 404, "temporary edge miss", {}, None),
            FakeResponse(b"<html>NSE</html>", "text/html"),
            FakeResponse(_fixture("equity_history_empty.json")),
        ])
        client = NseApiClient(opener=opener, max_retries=1, sleeper=lambda _: None)

        self.assertEqual(client.fetch_equity_history("EXAMPLE", date(2026, 9, 4), date(2026, 9, 4)), [])
        self.assertEqual(opener.requests[1].full_url, NseApiClient.HOME_URL)

    def test_html_success_page_is_rejected_for_file_download(self) -> None:
        client = NseApiClient(opener=QueueOpener([FakeResponse(_fixture("html_block_page.html"), "text/html")]))

        with self.assertRaisesRegex(NseResponseError, "HTML page") as error:
            client.download_equities_csv()

        self.assertEqual(error.exception.category, "HTML_BLOCK_PAGE")

    def test_bulk_report_downloads_use_exchange_archive_urls(self) -> None:
        opener = QueueOpener([
            FakeResponse(b"PK\x03\x04eod", "application/zip"),
            FakeResponse(b"MTO report", "text/plain"),
        ])
        client = NseApiClient(opener=opener)

        self.assertEqual(client.download_eod_report(date(2026, 9, 4)), b"PK\x03\x04eod")
        self.assertEqual(client.download_delivery_report(date(2026, 9, 4)), b"MTO report")
        self.assertIn("04092026", opener.requests[0].full_url)
        self.assertIn("MTO_04092026.DAT", opener.requests[1].full_url)

    def test_corporate_action_windows_are_cached_across_security_requests(self) -> None:
        opener = QueueOpener([FakeResponse(_fixture("corporate_actions.json"))])
        client = NseApiClient(
            opener=opener, max_history_days=100, sleeper=lambda _: None
        )

        first = client.fetch_corporate_actions(
            "EXAMPLE", date(2026, 9, 1), date(2026, 9, 5)
        )
        second = client.fetch_corporate_actions(
            "OTHER", date(2026, 9, 1), date(2026, 9, 5)
        )

        self.assertEqual(2, len(first))
        self.assertEqual(1, len(second))
        self.assertEqual(1, len(opener.requests))
        self.assertEqual(1, client.metrics["corporateActionCacheHits"])

    def test_corporate_action_window_without_symbol_returns_empty(self) -> None:
        opener = QueueOpener([FakeResponse(json.dumps({"data": [{
            "symbol": "OTHER", "exDate": "04-Sep-2026", "subject": "Dividend Rs 1",
        }]}).encode("utf-8"))])
        client = NseApiClient(opener=opener, sleeper=lambda _: None)

        records = client.fetch_corporate_actions(
            "EXAMPLE", date(2026, 9, 1), date(2026, 9, 4)
        )

        self.assertEqual([], records)


class NseNormalizationTestCase(unittest.TestCase):
    def test_corporate_actions_cover_supported_types_and_ignore_other_symbols(self) -> None:
        records = parse_corporate_actions_response(json.loads(_fixture("corporate_actions.json")), "EXAMPLE")

        self.assertEqual([record.action_type for record in records], [
            "DIVIDEND", "BONUS", "SPLIT", "RIGHTS", "CONSOLIDATION", "BUYBACK",
            "SCHEME_OF_ARRANGEMENT",
        ])
        self.assertEqual(records[0].cash_value, Decimal("5.00"))
        self.assertEqual((records[1].numerator, records[1].denominator), (Decimal("1"), Decimal("2")))

    def test_corporate_action_key_is_stable_when_payload_metadata_changes(self) -> None:
        original = {"data": [{"symbol": "EXAMPLE", "exDate": "04-Sep-2026", "subject": "Dividend - Rs. 5.00", "note": "first"}]}
        revised = {"data": [{"symbol": "EXAMPLE", "exDate": "04-Sep-2026", "subject": "Dividend - Rs. 5.00", "note": "revised"}]}

        original_record = parse_corporate_actions_response(original, "EXAMPLE")[0]
        revised_record = parse_corporate_actions_response(revised, "EXAMPLE")[0]
        self.assertEqual(original_record.source_event_key, revised_record.source_event_key)
        self.assertNotEqual(original_record.source_checksum, revised_record.source_checksum)

    def test_face_value_split_description_produces_price_multiplier(self) -> None:
        payload = {"data": [{
            "symbol": "SHAREINDIA",
            "exDate": "27-Jun-2024",
            "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
        }]}

        record = parse_corporate_actions_response(payload, "SHAREINDIA")[0]

        self.assertEqual(record.action_type, "SPLIT")
        self.assertEqual((record.numerator, record.denominator), (Decimal("2"), Decimal("10")))

    def test_re_abbreviation_composite_and_rights_terms_are_normalized(self) -> None:
        payload = {"data": [
            {"symbol": "EXAMPLE", "exDate": "01-Jan-2026", "faceVal": "10",
             "subject": "Fv Splt Frm Rs 10 To Re 1"},
            {"symbol": "EXAMPLE", "exDate": "02-Jan-2026", "faceVal": "10",
             "subject": "Bonus 1:1/Face Value Split From Rs 10 To Rs 2"},
            {"symbol": "EXAMPLE", "exDate": "03-Jan-2026", "faceVal": "10",
             "subject": "Rights 1:15 @ Premium Rs 1247"},
            {"symbol": "EXAMPLE", "exDate": "04-Jan-2026", "faceVal": "10",
             "subject": "Scheme Of Arrangement - Bonus Ncrps 4:1"},
            {"symbol": "EXAMPLE", "exDate": "05-Jan-2026", "faceVal": "10",
             "subject": "Rights 1:5 at Issue Price Rs 125"},
            {"symbol": "EXAMPLE", "exDate": "06-Jan-2026", "faceVal": "10",
             "subject": "Rights 1:5 @ Premium Of Rs 90"},
        ]}

        split, composite, rights, non_equity, direct_price, premium_of = parse_corporate_actions_response(
            payload, "EXAMPLE"
        )

        self.assertEqual(split.action_type, "SPLIT")
        self.assertEqual((split.numerator, split.denominator), (Decimal("1"), Decimal("10")))
        self.assertEqual(composite.action_type, "BONUS_SPLIT")
        self.assertEqual((composite.old_face_value, composite.new_face_value), (Decimal("10"), Decimal("2")))
        self.assertEqual(rights.issue_price, Decimal("1257"))
        self.assertEqual(non_equity.action_type, "NON_EQUITY_DISTRIBUTION")
        self.assertEqual(direct_price.issue_price, Decimal("125"))
        self.assertEqual(premium_of.issue_price, Decimal("100"))

    def test_malformed_history_fields_have_contextual_validation_errors(self) -> None:
        for fixture_name, expected_field in (
            ("equity_history_malformed_price.json", "ch_opening_price"),
            ("equity_history_malformed_date.json", "ch_timestamp"),
            ("equity_history_malformed_volume.json", "ch_tot_traded_qty"),
        ):
            with self.subTest(fixture=fixture_name):
                with self.assertRaisesRegex(NseDataValidationError, f"{expected_field}.*") as error:
                    parse_equity_history_response(json.loads(_fixture(fixture_name)), "EXAMPLE")
                self.assertEqual(error.exception.symbol, "EXAMPLE")

    def test_symbol_change_keeps_ising_based_persistence_mapping_stable(self) -> None:
        record = parse_equity_history_response(json.loads(_fixture("equity_history_symbol_change.json")), "FORMER NAME")[0]

        repository_record = raw_bar_record(record, "ine000000001")
        self.assertEqual(record.symbol, "FORMER NAME")
        self.assertEqual(repository_record["isin"], "INE000000001")
        self.assertNotIn("CH_SYMBOL", repository_record)

    def test_historical_isin_version_maps_to_current_stable_security(self) -> None:
        payload = {"data": [{
            "CH_SYMBOL": "20MICRONS", "CH_ISIN": "INE144J01019", "CH_SERIES": "EQ",
            "CH_TIMESTAMP": "14-Sep-2016", "CH_OPENING_PRICE": "30",
            "CH_TRADE_HIGH_PRICE": "31", "CH_TRADE_LOW_PRICE": "29",
            "CH_CLOSING_PRICE": "30.5", "CH_TOT_TRADED_QTY": "1000",
        }]}
        record = parse_equity_history_response(payload, "20MICRONS")[0]

        repository_record = raw_bar_record(
            record, "INE144J01027", expected_symbol="20MICRONS"
        )

        self.assertEqual("INE144J01027", repository_record["isin"])
        self.assertEqual("INE144J01019", repository_record["source_isin"])

    def test_different_issuer_isin_is_still_rejected(self) -> None:
        payload = {"data": [{
            "CH_SYMBOL": "20MICRONS", "CH_ISIN": "INE999Z01019", "CH_SERIES": "EQ",
            "CH_TIMESTAMP": "14-Sep-2016", "CH_OPENING_PRICE": "30",
            "CH_TRADE_HIGH_PRICE": "31", "CH_TRADE_LOW_PRICE": "29",
            "CH_CLOSING_PRICE": "30.5", "CH_TOT_TRADED_QTY": "1000",
        }]}
        record = parse_equity_history_response(payload, "20MICRONS")[0]

        with self.assertRaisesRegex(NseDataValidationError, "validated historical version"):
            raw_bar_record(record, "INE144J01027", expected_symbol="20MICRONS")


if __name__ == "__main__":
    unittest.main()
