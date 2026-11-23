"""Webclaw SDK exceptions."""

from __future__ import annotations


class WebclawError(Exception):
    """Base exception for all Webclaw API errors.

    ``request_id`` is the server request id from the ``x-request-id`` header or
    the error body's ``request_id``, or ``None`` when the API returned neither.
    """

    def __init__(self, message: str, status_code: int | None = None, request_id: str | None = None) -> None:
        self.status_code = status_code
        self.request_id = request_id
        super().__init__(f"{message} (request id: {request_id})" if request_id else message)


class AuthenticationError(WebclawError):
    """Raised on 401 responses -- invalid or missing API key."""

    def __init__(self, message: str = "Invalid or missing API key", request_id: str | None = None) -> None:
        super().__init__(message, status_code=401, request_id=request_id)


class ScopeError(AuthenticationError):
    """Raised on 403 responses -- authenticated but not authorized.

    This subclasses :class:`AuthenticationError` for compatibility with code
    that previously caught 401 and 403 together, while preserving the real
    HTTP status and allowing callers to distinguish plan/scope failures.
    """

    def __init__(self, message: str = "Insufficient permissions", request_id: str | None = None) -> None:
        WebclawError.__init__(self, message, status_code=403, request_id=request_id)


class RateLimitError(WebclawError):
    """Raised on 429 responses -- too many requests."""

    def __init__(self, message: str = "Rate limit exceeded", request_id: str | None = None) -> None:
        super().__init__(message, status_code=429, request_id=request_id)


class NotFoundError(WebclawError):
    """Raised on 404 responses."""

    def __init__(self, message: str = "Resource not found", request_id: str | None = None) -> None:
        super().__init__(message, status_code=404, request_id=request_id)


class TimeoutError(WebclawError):
    """Raised when a crawl job exceeds the wait timeout."""

    def __init__(self, message: str = "Operation timed out") -> None:
        super().__init__(message)
