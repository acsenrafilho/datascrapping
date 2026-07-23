from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from datascrapping.core.rate_limit import polite_sleep

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


class HttpClient:
    """requests session with retries and polite delays between calls."""

    def __init__(
        self,
        delay_min: float = 1.0,
        delay_max: float = 3.0,
        timeout: float = 20.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.timeout = timeout
        self.session = requests.Session()
        merged = dict(DEFAULT_HEADERS)
        if headers:
            merged.update(headers)
        self.session.headers.update(merged)

        retry = Retry(
            total=3,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self._first = True

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        if not self._first:
            waited = polite_sleep(self.delay_min, self.delay_max)
            logger.debug("Polite delay %.2fs before GET %s", waited, url)
        self._first = False
        timeout = kwargs.pop("timeout", self.timeout)
        response = self.session.get(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response

    def close(self) -> None:
        self.session.close()
