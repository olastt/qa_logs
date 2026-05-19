from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

_RETRYABLE = frozenset({429, 502, 503, 504})


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_retries: int = 6,
    retry_base_sec: float = 2.0,
    **kwargs: Any,
) -> httpx.Response:
    """Повтор при 429/5xx с учётом Retry-After."""
    last: httpx.Response | None = None
    for attempt in range(max_retries):
        response = client.request(method, url, **kwargs)
        last = response
        if response.status_code not in _RETRYABLE:
            return response

        wait = _wait_seconds(response, attempt, retry_base_sec)
        log.warning(
            "api_rate_limited",
            status=response.status_code,
            url=url,
            attempt=attempt + 1,
            wait_sec=wait,
        )
        time.sleep(wait)

    assert last is not None
    return last


def _wait_seconds(response: httpx.Response, attempt: int, base: float) -> float:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return min(float(raw), 120.0)
        except ValueError:
            pass
    return min(base * (2**attempt), 60.0)
