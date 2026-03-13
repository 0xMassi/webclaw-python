"""Webclaw Python SDK -- web extraction API client."""

from .async_client import AsyncCrawlJobHandle, AsyncWebclaw
from .client import CrawlJobHandle, Webclaw
from .errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
    WebclawError,
)
from .types import (
    BatchResponse,
    BatchResult,
    BrandResponse,
    CacheInfo,
    CrawlJob,
    CrawlPage,
    CrawlStatus,
    ExtractResponse,
    MapResponse,
    ScrapeResponse,
    SummarizeResponse,
)

__all__ = [
    # clients
    "Webclaw",
    "AsyncWebclaw",
    "CrawlJobHandle",
    "AsyncCrawlJobHandle",
    # types
    "BatchResponse",
    "BatchResult",
    "BrandResponse",
    "CacheInfo",
    "CrawlJob",
    "CrawlPage",
    "CrawlStatus",
    "ExtractResponse",
    "MapResponse",
    "ScrapeResponse",
    "SummarizeResponse",
    # errors
    "WebclawError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "TimeoutError",
]
