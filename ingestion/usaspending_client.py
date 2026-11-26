"""Thin, well-behaved client for the public USAspending API (no auth required)."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.usaspending.gov"
DEFAULT_TIMEOUT = 60


def build_session(user_agent: str = "fedspend-portfolio-project/0.1") -> requests.Session:
    """Session with retries and backoff for transient errors and rate limiting.

    HEAD and POST are included in the retry list because the requests we make with them are
    read-only (safe to repeat).
    """
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD", "POST"}),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": user_agent})
    return session


class USAspendingClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or build_session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(self._url(path), params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(self._url(path), json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def remote_size(self, url: str) -> tuple[int | None, str]:
        """Size in bytes of a remote file without downloading it: (size, note).

        Uses a one-byte ranged GET and reads the total from Content-Range. HEAD is only a
        fallback, because files.usaspending.gov (behind a load balancer) often drops HEAD
        connections ("Empty reply from server"). Each request asks the server to close the
        connection, so one dropped connection can't poison later requests.
        On failure returns (None, reason).
        """
        note = ""
        try:
            response = self.session.get(
                url,
                headers={"Range": "bytes=0-0", "Connection": "close"},
                stream=True,
                allow_redirects=True,
                timeout=self.timeout,
            )
            try:
                if response.status_code == 206:
                    total = response.headers.get("Content-Range", "").rsplit("/", 1)[-1]
                    if total.isdigit():
                        return int(total), ""
                elif response.status_code == 200:
                    length = response.headers.get("Content-Length")
                    if length is not None and length.isdigit():
                        return int(length), ""
                note = f"ranged GET status {response.status_code}"
            finally:
                response.close()
        except requests.RequestException as exc:
            note = f"ranged GET error {type(exc).__name__}: {str(exc)[:80]}"

        try:
            response = self.session.head(
                url,
                headers={"Connection": "close"},
                allow_redirects=True,
                timeout=self.timeout,
            )
            length = response.headers.get("Content-Length")
            if response.status_code < 400 and length is not None and length.isdigit():
                return int(length), ""
            note += f"; HEAD status {response.status_code}"
        except requests.RequestException as exc:
            note += f"; HEAD error {type(exc).__name__}"
        return None, note

    # --- Endpoints used for discovery -------------------------------------------------

    def list_agencies(self, agency_type: str = "award_agencies") -> dict[str, Any]:
        """Agencies available for bulk award downloads."""
        return self.post("/api/v2/bulk_download/list_agencies/", {"type": agency_type})

    def list_monthly_files(
        self, agency: int | str, fiscal_year: int, file_type: str
    ) -> dict[str, Any]:
        """Pre-generated monthly archive files (Full and Delta) for one agency/year/type."""
        payload = {"agency": agency, "fiscal_year": fiscal_year, "type": file_type}
        return self.post("/api/v2/bulk_download/list_monthly_files/", payload)
