"""Webclaw SDK exceptions."""

from __future__ import annotations


class WebclawError(Exception):
    """Base exception for all Webclaw API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(WebclawError):
    """Raised on 401/403 responses -- invalid or missing API key."""

    def __init__(self, message: str = "Invalid or missing API key") -> None:
        super().__init__(message, status_code=401)


class RateLimitError(WebclawError):
    """Raised on 429 responses -- too many requests."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, status_code=429)


class NotFoundError(WebclawError):
    """Raised on 404 responses."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class TimeoutError(WebclawError):
    """Raised when a crawl job exceeds the wait timeout."""

    def __init__(self, message: str = "Operation timed out") -> None:
        super().__init__(message)
