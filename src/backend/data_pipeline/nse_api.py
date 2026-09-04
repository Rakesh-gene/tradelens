from __future__ import annotations

import http.cookiejar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


class NseApiClient:
    """HTTP client for NSE endpoints.

    NSE requests need a browser user-agent. Some NSE endpoints also need an
    initial visit to the NSE site to obtain cookies. Keep this exchange-specific
    behaviour here rather than in collectors.
    """

    HOME_URL = "https://www.nseindia.com/"
    EQUITIES_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    # NSE rejects generic HTTP library user agents. This matches a current
    # desktop browser.
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout_seconds: float = 20) -> None:
        self._timeout_seconds = timeout_seconds
        self._opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._session_ready = False

    def download_equities_csv(self) -> bytes:
        """Download the current NSE equity master CSV."""
        try:
            return self._download_equities_csv()
        except HTTPError as error:
            if error.code != 403 or self._session_ready:
                raise
        self._ensure_session()
        return self._download_equities_csv()

    def _download_equities_csv(self) -> bytes:
        request = Request(
            self.EQUITIES_URL,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": self.HOME_URL,
            },
        )
        with self._opener.open(request, timeout=self._timeout_seconds) as response:
            return response.read()

    def _ensure_session(self) -> None:
        if self._session_ready:
            return
        request = Request(self.HOME_URL, headers={"User-Agent": self.USER_AGENT})
        with self._opener.open(request, timeout=self._timeout_seconds):
            pass
        self._session_ready = True
