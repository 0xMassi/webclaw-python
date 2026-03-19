"""Response types for the Webclaw API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# -- Scrape ------------------------------------------------------------------

@dataclass
class CacheInfo:
    status: str  # "hit" | "miss" | "bypass"


@dataclass
class ScrapeResponse:
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    markdown: str | None = None
    text: str | None = None
    llm: str | None = None
    json_data: Any | None = None
    cache: CacheInfo | None = None
    warning: str | None = None


# -- Crawl -------------------------------------------------------------------

@dataclass
class CrawlPage:
    url: str
    markdown: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class CrawlJob:
    """Returned immediately when a crawl is started."""
    id: str
    status: str  # "running"


@dataclass
class CrawlStatus:
    """Full crawl status including page results."""
    id: str
    status: str  # "running" | "completed" | "failed"
    pages: list[CrawlPage] = field(default_factory=list)
    total: int = 0
    completed: int = 0
    errors: int = 0


# -- Map ---------------------------------------------------------------------

@dataclass
class MapResponse:
    urls: list[str] = field(default_factory=list)
    count: int = 0


# -- Batch -------------------------------------------------------------------

@dataclass
class BatchResult:
    url: str
    markdown: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class BatchResponse:
    results: list[BatchResult] = field(default_factory=list)


# -- Extract -----------------------------------------------------------------

@dataclass
class ExtractResponse:
    data: Any = None


# -- Summarize ---------------------------------------------------------------

@dataclass
class SummarizeResponse:
    summary: str = ""


# -- Brand -------------------------------------------------------------------

@dataclass
class BrandResponse:
    """Brand identity -- structure depends on the API, so we store raw data."""
    data: dict[str, Any] = field(default_factory=dict)


# -- Search ------------------------------------------------------------------

@dataclass
class SearchResult:
    title: str = ""
    url: str = ""
    description: str = ""


@dataclass
class SearchResponse:
    results: list[SearchResult] = field(default_factory=list)
    query: str = ""


# -- Diff --------------------------------------------------------------------

@dataclass
class DiffResponse:
    url: str = ""
    has_changed: bool = False
    diff: str = ""
    previous_hash: str = ""
    current_hash: str = ""


# -- Agent Scrape ------------------------------------------------------------

@dataclass
class AgentScrapeResponse:
    url: str = ""
    result: str = ""
    steps: list[str] = field(default_factory=list)


# -- Research ----------------------------------------------------------------

@dataclass
class ResearchStartResponse:
    id: str = ""
    status: str = ""


@dataclass
class ResearchFinding:
    claim: str = ""
    source: str = ""
    relevance: float = 0.0


@dataclass
class ResearchSource:
    url: str = ""
    title: str = ""
    summary: str = ""


@dataclass
class ResearchStatusResponse:
    id: str = ""
    status: str = ""
    query: str = ""
    report: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    elapsed_ms: int = 0


# -- Watch -------------------------------------------------------------------

@dataclass
class WatchEntry:
    """A single watch monitor."""
    id: str = ""
    url: str = ""
    name: str | None = None
    interval_minutes: int = 1440
    webhook_url: str | None = None
    status: str = ""
    last_checked: str | None = None
    created_at: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> WatchEntry:
        return WatchEntry(
            id=data.get("id", ""),
            url=data.get("url", ""),
            name=data.get("name"),
            interval_minutes=data.get("interval_minutes", 1440),
            webhook_url=data.get("webhook_url"),
            status=data.get("status", ""),
            last_checked=data.get("last_checked"),
            created_at=data.get("created_at", ""),
        )


@dataclass
class WatchListResponse:
    watches: list[WatchEntry] = field(default_factory=list)
    total: int = 0


@dataclass
class WatchCheckResponse:
    """Result of a manual watch check."""
    id: str = ""
    has_changed: bool = False
    diff: str | None = None
    checked_at: str = ""
