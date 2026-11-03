"""Exceptions that describe what went wrong when calling the upstream API."""


class UpstreamError(Exception):
    """The upstream API (BrasilAPI) failed in a way we cannot recover from."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class NotFoundUpstream(UpstreamError):
    """The upstream API says the resource does not exist (404). Never retried."""

    def __init__(self, message: str = "Resource not found upstream"):
        super().__init__(message, status_code=404)


class RetryableUpstream(UpstreamError):
    """Temporary failure: timeout, network error, 429 or 5xx. Safe to retry."""
