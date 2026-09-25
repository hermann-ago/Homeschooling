"""Authenticated Google REST calls with bounded retries.

Idempotent reads retry on 429/5xx and network errors with exponential backoff.
Non-idempotent writes retry only when Google definitely rejected them (429);
otherwise the failure is reported as *uncertain* so the store can check its
operation receipt instead of resending, which would duplicate records.
"""
from __future__ import annotations

import random
import time

import httpx

from storage.gateway import AuthorizationRequired, GoogleUnavailable

RETRY_STATUS = {429, 500, 502, 503, 504}


class GoogleRest:
    def __init__(self, auth, transport: httpx.BaseTransport | None = None, max_attempts: int = 5,
                 sleep=time.sleep):
        self.auth = auth
        self.max_attempts = max_attempts
        self.sleep = sleep
        self.http = httpx.Client(timeout=httpx.Timeout(30, connect=10), transport=transport)

    def request(self, method: str, url: str, *, idempotent: bool | None = None, **kwargs) -> httpx.Response:
        idempotent = method in ("GET", "HEAD") if idempotent is None else idempotent
        refreshed = False
        extra_headers = kwargs.pop("headers", {})
        for attempt in range(1, self.max_attempts + 1):
            headers = {**extra_headers, "Authorization": f"Bearer {self.auth.access_token(refreshed)}"}
            try:
                response = self.http.request(method, url, headers=headers, **kwargs)
            except httpx.ConnectError as error:
                if attempt == self.max_attempts:
                    raise GoogleUnavailable(f"Google is unreachable: {error}") from error
            except httpx.HTTPError as error:
                if not idempotent:
                    raise GoogleUnavailable(f"No response from Google: {error}", uncertain=True) from error
                if attempt == self.max_attempts:
                    raise GoogleUnavailable(f"No response from Google: {error}") from error
            else:
                if response.status_code == 401 and not refreshed:
                    refreshed = True
                    continue
                if response.status_code == 401:
                    raise AuthorizationRequired("Google rejected the stored authorization; a parent must reconnect")
                if response.status_code == 403 and _rate_limited(response):
                    pass  # treat like 429 below
                elif response.status_code == 403:
                    raise PermissionError(_message(response))
                elif response.status_code not in RETRY_STATUS:
                    if response.status_code >= 400:
                        if response.status_code == 404:
                            raise FileNotFoundError(_message(response))
                        raise ValueError(_message(response))
                    return response
                if not idempotent and response.status_code != 429 and not _rate_limited(response):
                    raise GoogleUnavailable(f"Google returned {response.status_code}", uncertain=True)
                if attempt == self.max_attempts:
                    raise GoogleUnavailable(f"Google is busy ({response.status_code}); will retry later")
            self.sleep(min(32.0, 2 ** (attempt - 1)) + random.random())
        raise GoogleUnavailable("Google request failed")


def _rate_limited(response) -> bool:
    try:
        errors = response.json().get("error", {}).get("errors", [])
    except ValueError:
        return False
    return any(e.get("reason") in ("rateLimitExceeded", "userRateLimitExceeded") for e in errors)


def _message(response) -> str:
    try:
        return response.json().get("error", {}).get("message") or response.text
    except ValueError:
        return response.text or f"Google returned {response.status_code}"
