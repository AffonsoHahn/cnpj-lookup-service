"""Cache-or-fetch logic, kept free of FastAPI/httpx so it is easy to test."""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from . import db
from .errors import NotFoundUpstream, UpstreamError

log = logging.getLogger("cnpj_service.service")


@dataclass
class LookupResult:
    payload: dict
    source: str  # "cache", "api" or "cache-stale"
    fetched_at: datetime


def is_fresh(fetched_at: datetime, ttl_seconds: int, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return (now - fetched_at).total_seconds() < ttl_seconds


def get_or_fetch(conn, kind: str, key: str, fetch: Callable[[str], dict], ttl_seconds: int) -> LookupResult:
    cached = db.get(conn, kind, key)

    if cached and is_fresh(cached["fetched_at"], ttl_seconds):
        log.info("cache hit kind=%s key=%s", kind, key)
        return LookupResult(cached["payload"], "cache", cached["fetched_at"])

    try:
        payload = fetch(key)
    except NotFoundUpstream:
        raise  # the resource really does not exist; do not serve old data
    except UpstreamError as exc:
        if cached:  # upstream is down: a stale answer beats no answer
            log.warning("upstream failed (%s); serving stale cache kind=%s key=%s", exc, kind, key)
            return LookupResult(cached["payload"], "cache-stale", cached["fetched_at"])
        raise

    fetched_at = db.save(conn, kind, key, payload)
    log.info("fetched from api and cached kind=%s key=%s", kind, key)
    return LookupResult(payload, "api", fetched_at)
