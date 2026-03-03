"""
External Data Connectors — integrations with third-party procurement APIs.

Provides:
  - OpenCorporates API (vendor registration lookup)
  - OCDS API (Open Contracting Data Standard feeds)
  - World Bank procurement API
  - Generic REST connector with retry logic and rate limiting
"""

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("sunlight.external_data")


# ---------------------------------------------------------------------------
# Generic REST connector with retry + rate limiting
# ---------------------------------------------------------------------------

@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    requests_per_second: float = 5.0
    burst_limit: int = 10
    retry_max: int = 3
    retry_backoff_base: float = 1.0  # seconds
    timeout: float = 30.0  # seconds


class RESTConnector:
    """Generic REST API client with retry logic and rate limiting."""

    def __init__(
        self,
        base_url: str,
        headers: Optional[dict] = None,
        rate_config: Optional[RateLimitConfig] = None,
        api_key: Optional[str] = None,
        api_key_header: str = "Authorization",
    ):
        self.base_url = base_url.rstrip("/")
        self.rate_config = rate_config or RateLimitConfig()
        self._last_request_time = 0.0
        self._min_interval = 1.0 / self.rate_config.requests_per_second

        default_headers = {"Accept": "application/json", "User-Agent": "SUNLIGHT/2.0"}
        if headers:
            default_headers.update(headers)
        if api_key:
            default_headers[api_key_header] = api_key

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=default_headers,
            timeout=self.rate_config.timeout,
            follow_redirects=True,
        )

    def _rate_limit_wait(self):
        """Enforce rate limiting between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET request with retry logic."""
        return self._request("GET", path, params=params)

    def post(self, path: str, json_data: Optional[dict] = None) -> dict:
        """POST request with retry logic."""
        return self._request("POST", path, json_data=json_data)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        """Execute an HTTP request with retry and rate limiting."""
        last_error = None

        for attempt in range(self.rate_config.retry_max):
            self._rate_limit_wait()
            try:
                response = self._client.request(
                    method, path, params=params, json=json_data
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                last_error = e
                if status == 429:
                    # Rate limited — use Retry-After header if available
                    retry_after = float(
                        e.response.headers.get("Retry-After", self.rate_config.retry_backoff_base * (2 ** attempt))
                    )
                    logger.warning(f"Rate limited on {path}, retrying in {retry_after:.1f}s")
                    time.sleep(retry_after)
                    continue
                if status >= 500:
                    # Server error — retry with backoff
                    wait = self.rate_config.retry_backoff_base * (2 ** attempt)
                    logger.warning(f"Server error {status} on {path}, retrying in {wait:.1f}s")
                    time.sleep(wait)
                    continue
                # Client error (4xx except 429) — don't retry
                raise
            except httpx.TimeoutException as e:
                last_error = e
                wait = self.rate_config.retry_backoff_base * (2 ** attempt)
                logger.warning(f"Timeout on {path}, retrying in {wait:.1f}s (attempt {attempt + 1})")
                time.sleep(wait)
            except httpx.RequestError as e:
                last_error = e
                wait = self.rate_config.retry_backoff_base * (2 ** attempt)
                logger.warning(f"Request error on {path}: {e}, retrying in {wait:.1f}s")
                time.sleep(wait)

        raise ConnectionError(
            f"Failed after {self.rate_config.retry_max} attempts on {method} {path}: {last_error}"
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ---------------------------------------------------------------------------
# OpenCorporates — vendor registration lookup
# ---------------------------------------------------------------------------

OPENCORPORATES_BASE = "https://api.opencorporates.com/v0.4"


class OpenCorporatesClient:
    """Look up vendor registration details via the OpenCorporates API."""

    def __init__(self, api_token: Optional[str] = None):
        headers = {}
        if api_token:
            headers["Authorization"] = f"Token {api_token}"
        self._connector = RESTConnector(
            base_url=OPENCORPORATES_BASE,
            headers=headers,
            rate_config=RateLimitConfig(requests_per_second=2.0, retry_max=3),
        )

    def search_companies(self, query: str, jurisdiction: str = "", page: int = 1) -> dict:
        """Search for companies by name.

        Returns:
            {"companies": [...], "total_count": int, "page": int}
        """
        params = {"q": query, "page": page}
        if jurisdiction:
            params["jurisdiction_code"] = jurisdiction
        result = self._connector.get("/companies/search", params=params)
        companies = result.get("results", {}).get("companies", [])
        total = result.get("results", {}).get("total_count", 0)
        return {
            "companies": [c.get("company", c) for c in companies],
            "total_count": total,
            "page": page,
        }

    def get_company(self, jurisdiction: str, company_number: str) -> dict:
        """Get detailed company information.

        Returns:
            Company details including officers, filings, etc.
        """
        result = self._connector.get(
            f"/companies/{jurisdiction}/{company_number}"
        )
        return result.get("results", {}).get("company", {})

    def get_officers(self, jurisdiction: str, company_number: str) -> list:
        """Get company officers/directors."""
        result = self._connector.get(
            f"/companies/{jurisdiction}/{company_number}/officers"
        )
        officers = result.get("results", {}).get("officers", [])
        return [o.get("officer", o) for o in officers]

    def close(self):
        self._connector.close()


# ---------------------------------------------------------------------------
# OCDS — Open Contracting Data Standard
# ---------------------------------------------------------------------------

OCDS_DEFAULT_BASE = "https://standard.open-contracting.org/latest"


class OCDSClient:
    """Fetch procurement data from OCDS-compliant APIs."""

    def __init__(self, base_url: str = OCDS_DEFAULT_BASE, api_key: Optional[str] = None):
        self._connector = RESTConnector(
            base_url=base_url,
            api_key=api_key,
            rate_config=RateLimitConfig(requests_per_second=5.0, retry_max=3),
        )

    def get_releases(self, params: Optional[dict] = None) -> dict:
        """Fetch OCDS releases (planning, tender, award, contract, implementation).

        Returns:
            {"releases": [...], "next_page": str|None}
        """
        result = self._connector.get("/releases.json", params=params)
        return {
            "releases": result.get("releases", []),
            "next_page": result.get("links", {}).get("next"),
        }

    def get_release(self, ocid: str) -> dict:
        """Fetch a single OCDS release by OCID."""
        return self._connector.get(f"/releases/{ocid}")

    def get_records(self, params: Optional[dict] = None) -> dict:
        """Fetch OCDS records (compiled releases)."""
        result = self._connector.get("/records.json", params=params)
        return {
            "records": result.get("records", []),
            "next_page": result.get("links", {}).get("next"),
        }

    def close(self):
        self._connector.close()


# ---------------------------------------------------------------------------
# World Bank Procurement API
# ---------------------------------------------------------------------------

WORLD_BANK_BASE = "https://search.worldbank.org/api/v2/procnotices"


class WorldBankProcurementClient:
    """Fetch procurement notices from the World Bank API."""

    def __init__(self):
        self._connector = RESTConnector(
            base_url=WORLD_BANK_BASE,
            rate_config=RateLimitConfig(requests_per_second=3.0, retry_max=3),
        )

    def search_notices(
        self,
        query: str = "",
        country: str = "",
        procurement_type: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Search procurement notices.

        Args:
            query: Free-text search.
            country: ISO country code filter.
            procurement_type: e.g. "goods", "works", "consulting_services".
            page: Page number.
            page_size: Results per page.

        Returns:
            {"notices": [...], "total": int, "page": int}
        """
        params = {
            "format": "json",
            "rows": page_size,
            "os": (page - 1) * page_size,
        }
        if query:
            params["qterm"] = query
        if country:
            params["countrycode"] = country
        if procurement_type:
            params["proctype"] = procurement_type

        result = self._connector.get("", params=params)
        notices = result.get("procnotices", {})
        total = result.get("total", 0)
        # Normalize: API returns dict with numeric keys
        notice_list = []
        if isinstance(notices, dict):
            for k, v in notices.items():
                if isinstance(v, dict):
                    notice_list.append(v)
        elif isinstance(notices, list):
            notice_list = notices

        return {"notices": notice_list, "total": total, "page": page}

    def get_notice(self, notice_id: str) -> dict:
        """Get a specific procurement notice by ID."""
        result = self._connector.get("", params={"id": notice_id, "format": "json"})
        notices = result.get("procnotices", {})
        if isinstance(notices, dict):
            for v in notices.values():
                if isinstance(v, dict):
                    return v
        return {}

    def close(self):
        self._connector.close()


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_connector(
    source: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> object:
    """Factory to create the appropriate external data connector.

    Args:
        source: One of "opencorporates", "ocds", "worldbank", or a custom base_url.
        api_key: Optional API key/token.
        base_url: Override the default base URL.

    Returns:
        The appropriate client instance.
    """
    if source == "opencorporates":
        return OpenCorporatesClient(api_token=api_key)
    elif source == "ocds":
        return OCDSClient(base_url=base_url or OCDS_DEFAULT_BASE, api_key=api_key)
    elif source == "worldbank":
        return WorldBankProcurementClient()
    elif base_url:
        return RESTConnector(base_url=base_url, api_key=api_key)
    else:
        raise ValueError(f"Unknown source: {source}. Provide a base_url for custom APIs.")
