"""NSE-specific HTTP access with browser session handling and bounded retries."""

from __future__ import annotations

from datetime import date, timedelta
import http.cookiejar
import json
import random
import socket
from threading import Lock, local
import time
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from data_pipeline.models import (
    NseCorporateActionRecord,
    NseEquityClassification,
    NseEquityHistoryRecord,
    NseIndexHistoryRecord,
)
from data_pipeline.normalization import (
    parse_corporate_actions_response,
    parse_equity_classification_response,
    parse_equity_history_response,
    parse_index_history_response,
)


class NseRequestError(RuntimeError):
    """A classified NSE transport or response failure safe to expose to a job log."""

    def __init__(self, category: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.status_code = status_code


class NseResponseError(NseRequestError):
    """NSE returned a successful HTTP response that is not the requested content."""


class NseApiClient:
    """HTTP client for NSE endpoints; collectors must not implement NSE protocol rules."""

    HOME_URL = "https://www.nseindia.com/"
    API_URL = "https://www.nseindia.com/api"
    EQUITIES_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    EQUITY_HISTORY_URL = f"{API_URL}/NextApi/apiClient/GetQuoteApi"
    CORPORATE_ACTIONS_URL = f"{API_URL}/corporates-corporateActions"
    INDEX_HISTORY_URL = f"{API_URL}/historical/indicesHistory"
    INDEX_HISTORY_FALLBACK_URL = "https://niftyindices.com/BackPage/getHistoricaldatatabletoString"
    EOD_REPORT_URL_TEMPLATE = (
        "https://nsearchives.nseindia.com/content/cm/"
        "BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
    )
    DELIVERY_REPORT_URL_TEMPLATE = "https://nsearchives.nseindia.com/archives/equities/mto/MTO_{date}.DAT"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        timeout_seconds: float = 20,
        *,
        max_retries: int = 3,
        max_requests_per_second: float = 2.0,
        max_history_days: int = 100,
        opener=None,
        opener_factory: Callable[[], object] | None = None,
        circuit_breaker_threshold: int = 6,
        circuit_breaker_cooldown_seconds: float = 30,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if max_requests_per_second <= 0:
            raise ValueError("max_requests_per_second must be positive")
        if max_history_days <= 0:
            raise ValueError("max_history_days must be positive")
        if opener is not None and opener_factory is not None:
            raise ValueError("opener and opener_factory cannot both be supplied")
        if circuit_breaker_threshold <= 0:
            raise ValueError("circuit_breaker_threshold must be positive")
        if circuit_breaker_cooldown_seconds < 0:
            raise ValueError("circuit_breaker_cooldown_seconds cannot be negative")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._request_interval_seconds = 1 / max_requests_per_second
        self._max_history_days = max_history_days
        self._injected_opener = opener
        self._opener_factory = opener_factory or self._build_opener
        self._thread_session = local()
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._random_value = random_value
        self._next_request_at = 0.0
        self._request_slot_lock = Lock()
        self._session_lock = Lock()
        self._circuit_lock = Lock()
        self._metrics_lock = Lock()
        self._circuit_breaker_threshold = circuit_breaker_threshold
        self._circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        self._consecutive_transport_failures = 0
        self._circuit_open_until = 0.0
        self._corporate_action_lock = Lock()
        self._corporate_action_cache: dict[tuple[date, date], object] = {}
        self._corporate_action_symbol_cache: dict[
            tuple[date, date], dict[str, list[Mapping[str, object]]]
        ] = {}
        self._metrics = {
            "requestAttempts": 0, "successfulRequests": 0,
            "rateLimitedRequests": 0, "blockedRequests": 0,
            "timeoutRequests": 0, "networkErrors": 0,
            "corporateActionCacheHits": 0,
            "sessionResets": 0, "circuitBreakerTrips": 0,
        }

    @property
    def metrics(self) -> dict[str, int]:
        """Return aggregate, secret-free source request counters for job metrics."""

        with self._metrics_lock:
            return dict(self._metrics)

    def download_equities_csv(self) -> bytes:
        """Download the NSE equity master CSV after validating it is not an error page."""

        return self._download_file(self.EQUITIES_URL, "equity master CSV")

    def fetch_equity_classification(
        self, symbol: str, expected_isin: str
    ) -> NseEquityClassification:
        """Return NSE's current four-level classification for an equity."""

        normalized_symbol = self._normalize_symbol(symbol)
        payload = self._request_json(
            self.EQUITY_HISTORY_URL,
            {"functionName": "getSymbolData", "marketType": "N",
             "series": "EQ", "symbol": normalized_symbol},
        )
        return parse_equity_classification_response(
            payload, normalized_symbol, expected_isin
        )

    def fetch_equity_history(
        self, symbol: str, from_date: date, to_date: date
    ) -> list[NseEquityHistoryRecord]:
        """Return validated equity-history DTOs in bounded NSE requests, without persistence."""

        normalized_symbol = self._normalize_symbol(symbol)
        records: list[NseEquityHistoryRecord] = []
        for chunk_from, chunk_to in self._date_chunks(from_date, to_date):
            payload = self._request_json(
                self.EQUITY_HISTORY_URL,
                {
                    "functionName": "getHistoricalTradeData",
                    "symbol": normalized_symbol,
                    "series": "EQ",
                    "fromDate": self._format_date(chunk_from),
                    "toDate": self._format_date(chunk_to),
                },
            )
            records.extend(parse_equity_history_response(payload, normalized_symbol))
        return self._deduplicate_history(records)

    def fetch_corporate_actions(
        self, symbol: str, from_date: date, to_date: date
    ) -> list[NseCorporateActionRecord]:
        """Return validated actions for a symbol without persisting them."""

        normalized_symbol = self._normalize_symbol(symbol)
        records: list[NseCorporateActionRecord] = []
        for chunk_from, chunk_to in self._aligned_date_chunks(from_date, to_date):
            key = (chunk_from, chunk_to)
            with self._corporate_action_lock:
                payload = self._corporate_action_cache.get(key)
                if payload is None:
                    payload = self._request_json(
                        self.CORPORATE_ACTIONS_URL,
                        {
                            "index": "equities",
                            "from_date": self._format_date(chunk_from),
                            "to_date": self._format_date(chunk_to),
                        },
                    )
                    self._corporate_action_cache[key] = payload
                    self._corporate_action_symbol_cache[key] = self._index_actions_by_symbol(payload)
                else:
                    self._increment_metric("corporateActionCacheHits")
                indexed = self._corporate_action_symbol_cache.get(key)
                if indexed is None:
                    indexed = self._index_actions_by_symbol(payload)
                    self._corporate_action_symbol_cache[key] = indexed
            records.extend(parse_corporate_actions_response(
                {"data": indexed.get(normalized_symbol, [])}, normalized_symbol
            ))
        requested = [record for record in records if from_date <= record.ex_date <= to_date]
        return self._deduplicate_actions(requested)

    def fetch_index_history(
        self, index_name: str, from_date: date, to_date: date
    ) -> list[NseIndexHistoryRecord]:
        """Return validated index history for the requested date range without persistence."""

        normalized_index = " ".join(index_name.strip().upper().split())
        if not normalized_index:
            raise ValueError("index_name is required")
        records: list[NseIndexHistoryRecord] = []
        use_fallback = False
        for chunk_from, chunk_to in self._date_chunks(from_date, to_date):
            if use_fallback:
                payload = self._request_index_history_fallback(
                    normalized_index, chunk_from, chunk_to
                )
            else:
                try:
                    payload = self._request_json(
                        self.INDEX_HISTORY_URL,
                        {
                            "indexType": normalized_index,
                            "from": self._format_date(chunk_from),
                            "to": self._format_date(chunk_to),
                        },
                    )
                    nested = payload.get("data") if isinstance(payload, Mapping) else None
                    if isinstance(nested, Mapping):
                        payload = nested.get("indexCloseOnlineRecords", [])
                except NseRequestError:
                    # NSE's public historical route intermittently returns 503.
                    # NSE Indices publishes the same official OHLC series.
                    use_fallback = True
                    payload = self._request_index_history_fallback(
                        normalized_index, chunk_from, chunk_to
                    )
            records.extend(parse_index_history_response(payload, normalized_index))
        unique = {(record.trading_date, record.index_name): record for record in records}
        return [unique[key] for key in sorted(unique)]

    def _request_index_history_fallback(
        self, index_name: str, from_date: date, to_date: date
    ) -> object:
        cinfo = (
            "{'name': '" + index_name + "', 'startDate': '"
            + from_date.strftime("%d-%b-%Y") + "', 'endDate': '"
            + to_date.strftime("%d-%b-%Y") + "', 'indexName': '"
            + index_name + "'}"
        )
        body, content_type = self._request_bytes(
            self.INDEX_HISTORY_FALLBACK_URL,
            "application/json, text/plain;q=0.9, */*;q=0.8",
            data=json.dumps({"cinfo": cinfo}).encode("utf-8"),
            extra_headers={
                "Content-Type": "application/json; charset=UTF-8",
                "Origin": "https://niftyindices.com",
                "Referer": "https://niftyindices.com/reports",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        # NSE Indices currently labels its JSON array as text/html. Validate
        # the body itself here while still rejecting a genuine block page.
        self._reject_empty_or_html_body(body, "NSE Indices JSON response")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NseResponseError("INVALID_JSON", "NSE Indices returned malformed JSON") from exc

    def download_eod_report(self, trading_date: date) -> bytes:
        """Download the NSE bulk EOD report when the archive has published it."""

        return self._download_file(
            self.EOD_REPORT_URL_TEMPLATE.format(date=trading_date.strftime("%d%m%Y")),
            f"EOD report for {trading_date.isoformat()}",
        )

    def download_delivery_report(self, trading_date: date) -> bytes:
        """Download the optional NSE delivery report when it is available."""

        return self._download_file(
            self.DELIVERY_REPORT_URL_TEMPLATE.format(date=trading_date.strftime("%d%m%Y")),
            f"delivery report for {trading_date.isoformat()}",
        )

    def _request_json(
        self, url: str, parameters: Mapping[str, str], *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> object:
        query = urlencode(parameters)
        body, content_type = self._request_bytes(
            f"{url}?{query}",
            "application/json, text/plain;q=0.9, */*;q=0.8",
            extra_headers=extra_headers,
        )
        self._validate_json_response(body, content_type)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NseResponseError("INVALID_JSON", "NSE returned malformed JSON") from exc

    def _download_file(self, url: str, description: str) -> bytes:
        body, content_type = self._request_bytes(
            url,
            "text/csv,application/zip,application/octet-stream,text/plain;q=0.9,*/*;q=0.8",
        )
        self._validate_file_response(body, content_type, description)
        return body

    def _request_bytes(
        self, url: str, accept: str, *, data: bytes | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> tuple[bytes, str | None]:
        last_error: NseRequestError | None = None
        for attempt in range(self._max_retries + 1):
            self._increment_metric("requestAttempts")
            try:
                response = self._open_once(
                    url, accept, data=data, extra_headers=extra_headers
                )
                self._record_transport_success()
                self._increment_metric("successfulRequests")
                return response
            except Exception as error:  # noqa: BLE001 - normalize transport exceptions at this boundary
                classified = self._classify_error(error)
                if classified.status_code == 429: self._increment_metric("rateLimitedRequests")
                if classified.status_code == 403 or classified.category == "HTML_BLOCK_PAGE": self._increment_metric("blockedRequests")
                if classified.category == "TIMEOUT": self._increment_metric("timeoutRequests")
                if classified.category in {"NETWORK_ERROR", "CONNECTION_RESET"}: self._increment_metric("networkErrors")
                if self._is_transport_failure(classified):
                    self._record_transport_failure()
                    self._reset_thread_session()
                if classified.status_code in {403, 404} and not self._session_is_ready():
                    self._ensure_session()
                    last_error = classified
                    continue
                last_error = classified
                if not self._is_retryable(classified) or attempt == self._max_retries:
                    raise classified from error
                self._backoff(attempt)
        raise last_error or NseRequestError("UNKNOWN", "NSE request failed")

    def _open_once(
        self, url: str, accept: str, *, data: bytes | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> tuple[bytes, str | None]:
        self._wait_for_circuit()
        # Only serialize reservation of a rate-limit slot. Holding this lock
        # while waiting for the response lets one slow NSE call stall every
        # equity worker and defeats bounded HTTP concurrency.
        with self._request_slot_lock:
            self._wait_for_request_slot()
        headers = self._headers(accept)
        headers.update(extra_headers or {})
        request = Request(url, headers=headers, data=data)
        with self._opener_for_thread().open(request, timeout=self._timeout_seconds) as response:
            status_code = getattr(response, "status", 200)
            if status_code >= 400:
                raise NseRequestError("HTTP_ERROR", f"NSE returned HTTP {status_code}", status_code=status_code)
            return response.read(), self._response_content_type(response)

    def _ensure_session(self) -> None:
        with self._session_lock:
            if self._session_is_ready():
                return
            self._open_once(self.HOME_URL, "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8")
            self._thread_session.session_ready = True

    @staticmethod
    def _build_opener():
        return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _opener_for_thread(self):
        if self._injected_opener is not None:
            return self._injected_opener
        opener = getattr(self._thread_session, "opener", None)
        if opener is None:
            opener = self._opener_factory()
            self._thread_session.opener = opener
            self._thread_session.session_ready = False
        return opener

    def _session_is_ready(self) -> bool:
        return bool(getattr(self._thread_session, "session_ready", False))

    def _reset_thread_session(self) -> None:
        # urllib openers own their CookieJar. Replacing the opener prevents a
        # stale or silently throttled NSE session from poisoning later work on
        # the same executor thread.
        if self._injected_opener is None:
            self._thread_session.opener = None
        self._thread_session.session_ready = False
        self._increment_metric("sessionResets")

    def _wait_for_circuit(self) -> None:
        with self._circuit_lock:
            delay = max(0.0, self._circuit_open_until - self._monotonic())
        if delay:
            self._sleeper(delay)

    def _record_transport_failure(self) -> None:
        with self._circuit_lock:
            self._consecutive_transport_failures += 1
            if self._consecutive_transport_failures < self._circuit_breaker_threshold:
                return
            self._consecutive_transport_failures = 0
            self._circuit_open_until = max(
                self._circuit_open_until,
                self._monotonic() + self._circuit_breaker_cooldown_seconds,
            )
        self._increment_metric("circuitBreakerTrips")

    def _record_transport_success(self) -> None:
        with self._circuit_lock:
            self._consecutive_transport_failures = 0
            self._circuit_open_until = 0.0

    def _increment_metric(self, name: str) -> None:
        with self._metrics_lock:
            self._metrics[name] += 1

    def _wait_for_request_slot(self) -> None:
        now = self._monotonic()
        if self._next_request_at > now:
            self._sleeper(self._next_request_at - now)
        self._next_request_at = self._monotonic() + self._request_interval_seconds

    def _backoff(self, attempt: int) -> None:
        base_delay = min(8.0, 0.25 * (2 ** attempt))
        self._sleeper(base_delay + (self._random_value() * 0.25))

    def _headers(self, accept: str) -> dict[str, str]:
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": self.HOME_URL,
            "Connection": "keep-alive",
        }

    @staticmethod
    def _response_content_type(response) -> str | None:
        headers = getattr(response, "headers", None)
        if headers is None:
            return None
        if hasattr(headers, "get_content_type"):
            return headers.get_content_type()
        value = headers.get("Content-Type") if hasattr(headers, "get") else None
        return str(value).split(";", maxsplit=1)[0].strip().lower() if value else None

    @staticmethod
    def _validate_json_response(body: bytes, content_type: str | None) -> None:
        NseApiClient._reject_html_or_empty(body, content_type, "JSON response")
        if content_type and "json" not in content_type and content_type not in {"text/plain", "application/octet-stream"}:
            raise NseResponseError("INVALID_CONTENT_TYPE", f"NSE returned {content_type} instead of JSON")

    @staticmethod
    def _validate_file_response(body: bytes, content_type: str | None, description: str) -> None:
        NseApiClient._reject_html_or_empty(body, content_type, description)

    @staticmethod
    def _reject_html_or_empty(body: bytes, content_type: str | None, description: str) -> None:
        stripped = body.lstrip().lower()
        if not stripped:
            raise NseResponseError("EMPTY_RESPONSE", f"NSE returned an empty {description}")
        if (content_type and "html" in content_type) or stripped.startswith(b"<!doctype html") or stripped.startswith(b"<html"):
            raise NseResponseError("HTML_BLOCK_PAGE", f"NSE returned an HTML page instead of {description}")

    @staticmethod
    def _reject_empty_or_html_body(body: bytes, description: str) -> None:
        stripped = body.lstrip().lower()
        if not stripped:
            raise NseResponseError("EMPTY_RESPONSE", f"NSE returned an empty {description}")
        if stripped.startswith((b"<!doctype html", b"<html")):
            raise NseResponseError("HTML_BLOCK_PAGE", f"NSE returned an HTML page instead of {description}")

    @staticmethod
    def _classify_error(error: Exception) -> NseRequestError:
        if isinstance(error, NseRequestError):
            return error
        if isinstance(error, HTTPError):
            category = "RATE_LIMITED" if error.code == 429 else "ACCESS_DENIED" if error.code == 403 else "HTTP_ERROR"
            return NseRequestError(category, f"NSE returned HTTP {error.code}", status_code=error.code)
        if isinstance(error, (socket.timeout, TimeoutError)):
            return NseRequestError("TIMEOUT", "NSE request timed out")
        if isinstance(error, ConnectionResetError):
            return NseRequestError("CONNECTION_RESET", "NSE reset the connection")
        if isinstance(error, URLError):
            if isinstance(error.reason, (socket.timeout, TimeoutError)):
                return NseRequestError("TIMEOUT", "NSE request timed out")
            if isinstance(error.reason, ConnectionResetError):
                return NseRequestError("CONNECTION_RESET", "NSE reset the connection")
            return NseRequestError("NETWORK_ERROR", "NSE network request failed")
        return NseRequestError("UNKNOWN", "NSE request failed")

    @staticmethod
    def _is_retryable(error: NseRequestError) -> bool:
        return (
            error.status_code in {403, 404, 429}
            or error.status_code is not None and error.status_code >= 500
            or error.category in {"TIMEOUT", "CONNECTION_RESET", "NETWORK_ERROR"}
        )

    @staticmethod
    def _is_transport_failure(error: NseRequestError) -> bool:
        return error.category in {"TIMEOUT", "CONNECTION_RESET", "NETWORK_ERROR"}

    def _date_chunks(self, from_date: date, to_date: date) -> list[tuple[date, date]]:
        if from_date > to_date:
            raise ValueError("from_date cannot be after to_date")
        chunks: list[tuple[date, date]] = []
        chunk_from = from_date
        while chunk_from <= to_date:
            chunk_to = min(chunk_from + timedelta(days=self._max_history_days - 1), to_date)
            chunks.append((chunk_from, chunk_to))
            chunk_from = chunk_to + timedelta(days=1)
        return chunks

    def _aligned_date_chunks(self, from_date: date, to_date: date) -> list[tuple[date, date]]:
        """Return stable request windows so universe-wide responses can be reused."""
        if from_date > to_date:
            raise ValueError("from_date cannot be after to_date")
        ordinal = from_date.toordinal()
        bucket_start = ordinal - ((ordinal - 1) % self._max_history_days)
        chunks = []
        while bucket_start <= to_date.toordinal():
            chunk_from = date.fromordinal(bucket_start)
            chunk_to = min(
                date.fromordinal(bucket_start + self._max_history_days - 1), to_date
            )
            chunks.append((chunk_from, chunk_to))
            bucket_start += self._max_history_days
        return chunks

    @staticmethod
    def _format_date(value: date) -> str:
        return value.strftime("%d-%m-%Y")

    @staticmethod
    def _normalize_symbol(value: str) -> str:
        normalized = " ".join(value.strip().upper().split())
        if not normalized:
            raise ValueError("symbol is required")
        return normalized

    @staticmethod
    def _deduplicate_history(records: list[NseEquityHistoryRecord]) -> list[NseEquityHistoryRecord]:
        unique = {(record.trading_date, record.symbol, record.series): record for record in records}
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _deduplicate_actions(records: list[NseCorporateActionRecord]) -> list[NseCorporateActionRecord]:
        unique = {record.source_event_key: record for record in records}
        return sorted(unique.values(), key=lambda record: (record.ex_date, record.source_event_key))

    @staticmethod
    def _index_actions_by_symbol(payload: object) -> dict[str, list[Mapping[str, object]]]:
        if isinstance(payload, Mapping):
            values = payload.get("data", payload.get("records", ()))
        else:
            values = payload
        if isinstance(values, Mapping):
            if not values:
                values = ()
            else:
                values = next((
                    values[key] for key in ("data", "records", "rows", "content")
                    if isinstance(values.get(key), (list, tuple))
                ), ())
        if not isinstance(values, (list, tuple)):
            return {}
        result: dict[str, list[Mapping[str, object]]] = {}
        for row in values:
            if not isinstance(row, Mapping):
                continue
            symbol = next((
                value for key, value in row.items()
                if str(key).replace("_", "").lower() in {"symbol", "chsymbol"}
            ), None)
            normalized = " ".join(str(symbol or "").strip().upper().split())
            if normalized:
                result.setdefault(normalized, []).append(row)
        return result
