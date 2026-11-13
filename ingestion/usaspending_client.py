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

    POST is included in the retry list because the endpoints we call with POST are
    read-only queries (safe to repeat).
    """
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
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

    def head_content_length(self, url: str) -> int | None:
        """Size in bytes of a remote file via HEAD (no download). None if unavailable."""
        try:
            response = self.session.head(url, allow_redirects=True, timeout=self.timeout)
            response.raise_for_status()
            length = response.headers.get("Content-Length")
            return int(length) if length is not None else None
        except (requests.RequestException, ValueError):
            return None

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
