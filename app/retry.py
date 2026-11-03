"""Retry with exponential backoff for temporary upstream failures."""
import logging
import random
import time
from typing import Callable, Tuple, Type, TypeVar

from .errors import RetryableUpstream

log = logging.getLogger("cnpj_service.retry")
T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: Tuple[Type[Exception], ...] = (RetryableUpstream,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call func(); on a retryable error wait base_delay * 2^n (plus a little jitter) and try again."""
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except retry_on as exc:
            if attempt == attempts:
                log.error("giving up after %d attempts: %s", attempts, exc)
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            delay += random.uniform(0, delay * 0.1)
            log.warning("attempt %d/%d failed (%s); retrying in %.2fs", attempt, attempts, exc, delay)
            sleep(delay)
    raise RuntimeError("attempts must be >= 1")  # pragma: no cover
