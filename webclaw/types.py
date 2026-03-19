"""Response types for the Webclaw API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# -- Scrape ------------------------------------------------------------------

@dataclass
class CacheInfo:
    status: str  # "hit" | "miss" | "bypass"


@dataclass
class ScrapeResponse:
    url: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    markdown: Optional[str] = None
    text: Optional[str] = None
    llm: Optional[str] = None
    json_data: Optional[Any] = None
    cache: Optional[CacheInfo] = None
    warning: Optional[str] = None


# -- Crawl -------------------------------------------------------------------

@dataclass
class CrawlPage:
    url: str
    markdown: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


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
    pages: List[CrawlPage] = field(default_factory=list)
    total: int = 0
    completed: int = 0
    errors: int = 0


# -- Map ---------------------------------------------------------------------

@dataclass
class MapResponse:
    urls: List[str] = field(default_factory=list)
    count: int = 0


# -- Batch -------------------------------------------------------------------

@dataclass
class BatchResult:
    url: str
    markdown: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class BatchResponse:
    results: List[BatchResult] = field(default_factory=list)


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
    data: Dict[str, Any] = field(default_factory=dict)


# -- Search ------------------------------------------------------------------

@dataclass
class SearchResult:
    title: str = ""
    url: str = ""
    description: str = ""


@dataclass
class SearchResponse:
    results: List[SearchResult] = field(default_factory=list)
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
    steps: List[str] = field(default_factory=list)


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
    sources: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    elapsed_ms: int = 0
