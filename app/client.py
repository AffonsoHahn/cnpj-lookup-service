"""Thin HTTP client for BrasilAPI with timeouts, error mapping and retries."""
import logging
import time
from typing import Optional

import httpx

from .errors import NotFoundUpstream, RetryableUpstream, UpstreamError
from .retry import retry_with_backoff

log = logging.getLogger("cnpj_service.client")


class BrasilAPIClient:
    def __init__(
        self,
        base_url: str = "https://brasilapi.com.br/api",
        timeout: float = 10.0,
        attempts: int = 3,
        base_delay: float = 0.5,
        http_client: Optional[httpx.Client] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.attempts = attempts
        self.base_delay = base_delay
        self._http = http_client or httpx.Client(timeout=timeout)

    def _get_once(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        started = time.perf_counter()
        try:
            response = self._http.get(url)
        except httpx.TimeoutException as exc:
            raise RetryableUpstream(f"timeout calling {url}", status_code=504) from exc
        except httpx.RequestError as exc:
            raise RetryableUpstream(f"network error calling {url}: {exc}", status_code=502) from exc
        finally:
            log.info("GET %s took %.0f ms", url, (time.perf_counter() - started) * 1000)

        status = response.status_code
        if status == 200:
            return response.json()
        if status == 404:
            raise NotFoundUpstream(f"{url} returned 404")
        if status == 429:
            raise RetryableUpstream("upstream rate limit (429)", status_code=429)
        if status >= 500:
            raise RetryableUpstream(f"upstream error {status}", status_code=502)
        raise UpstreamError(f"unexpected upstream status {status}", status_code=502)

    def get_json(self, path: str) -> dict:
        return retry_with_backoff(
            lambda: self._get_once(path), attempts=self.attempts, base_delay=self.base_delay
        )

    def get_cnpj(self, cnpj: str) -> dict:
        return self.get_json(f"/cnpj/v1/{cnpj}")

    def get_cep(self, cep: str) -> dict:
        return self.get_json(f"/cep/v2/{cep}")

    def close(self) -> None:
        self._http.close()
