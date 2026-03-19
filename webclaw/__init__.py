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
    AgentScrapeResponse,
    BatchResponse,
    BatchResult,
    BrandResponse,
    CacheInfo,
    CrawlJob,
    CrawlPage,
    CrawlStatus,
    DiffResponse,
    ExtractResponse,
    MapResponse,
    ResearchFinding,
    ResearchSource,
    ResearchStartResponse,
    ResearchStatusResponse,
    ScrapeResponse,
    SearchResponse,
    SearchResult,
    SummarizeResponse,
    WatchCheckResponse,
    WatchEntry,
    WatchListResponse,
)

__all__ = [
    # clients
    "Webclaw",
    "AsyncWebclaw",
    "CrawlJobHandle",
    "AsyncCrawlJobHandle",
    # types
    "AgentScrapeResponse",
    "BatchResponse",
    "BatchResult",
    "BrandResponse",
    "CacheInfo",
    "CrawlJob",
    "CrawlPage",
    "CrawlStatus",
    "DiffResponse",
    "ExtractResponse",
    "MapResponse",
    "ResearchFinding",
    "ResearchSource",
    "ResearchStartResponse",
    "ResearchStatusResponse",
    "ScrapeResponse",
    "SearchResponse",
    "SearchResult",
    "SummarizeResponse",
    "WatchCheckResponse",
    "WatchEntry",
    "WatchListResponse",
    # errors
    "WebclawError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "TimeoutError",
]
