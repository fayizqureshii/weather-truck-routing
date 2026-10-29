"""Shared HTTP session for third-party APIs, with retries and a polite User-Agent."""

from __future__ import annotations

from functools import lru_cache

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class UpstreamError(Exception):
    """A third-party service failed or returned something unusable."""


@lru_cache(maxsize=1)
def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers["User-Agent"] = settings.HTTP_USER_AGENT
    return s


def get_json(url: str, params: dict | None = None, ok_statuses: tuple[int, ...] = ()) -> dict | list:
    """GET and decode JSON. `ok_statuses` lists error codes whose JSON body the caller handles."""
    try:
        resp = session().get(url, params=params, timeout=settings.HTTP_TIMEOUT_SECONDS)
        if resp.status_code not in ok_statuses:
            resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise UpstreamError(f"Request to {url.split('?')[0]} failed: {exc}") from exc
