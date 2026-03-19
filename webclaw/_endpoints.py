"""Shared request body builders and response parsers.

Both sync and async clients delegate to these functions so endpoint
logic lives in exactly one place.  Only the transport layer (sync
httpx vs async httpx) differs between the two clients.
"""

from __future__ import annotations

from typing import Any, Sequence

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
    ResearchStatusResponse,
    ScrapeResponse,
    SummarizeResponse,
    WatchCheckResponse,
    WatchEntry,
    WatchListResponse,
)

DEFAULT_BASE_URL = "https://api.webclaw.io"
DEFAULT_TIMEOUT = 30.0

# Terminal states shared by crawl and research polling.
TERMINAL_STATES = frozenset({"completed", "failed"})


# ---------------------------------------------------------------------------
# Request body builders
# ---------------------------------------------------------------------------

def build_scrape_body(
    url: str,
    *,
    formats: Sequence[str] | None = None,
    include_selectors: list[str] | None = None,
    exclude_selectors: list[str] | None = None,
    only_main_content: bool = False,
    no_cache: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {"url": url}
    if formats is not None:
        body["formats"] = list(formats)
    if include_selectors:
        body["include_selectors"] = include_selectors
    if exclude_selectors:
        body["exclude_selectors"] = exclude_selectors
    if only_main_content:
        body["only_main_content"] = True
    if no_cache:
        body["no_cache"] = True
    return body


def build_crawl_body(
    url: str,
    *,
    max_depth: int = 2,
    max_pages: int = 50,
    use_sitemap: bool = False,
) -> dict[str, Any]:
    return {
        "url": url,
        "max_depth": max_depth,
        "max_pages": max_pages,
        "use_sitemap": use_sitemap,
    }


def build_batch_body(
    urls: list[str],
    *,
    formats: Sequence[str] | None = None,
    concurrency: int = 5,
) -> dict[str, Any]:
    body: dict[str, Any] = {"urls": urls, "concurrency": concurrency}
    if formats is not None:
        body["formats"] = list(formats)
    return body


def build_extract_body(
    url: str,
    *,
    schema: dict[str, Any] | None = None,
    prompt: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"url": url}
    if schema is not None:
        body["schema"] = schema
    if prompt is not None:
        body["prompt"] = prompt
    return body


def build_summarize_body(
    url: str,
    *,
    max_sentences: int | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"url": url}
    if max_sentences is not None:
        body["max_sentences"] = max_sentences
    return body


def build_search_body(
    query: str,
    *,
    num_results: int | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query}
    if num_results is not None:
        body["num_results"] = num_results
    if topic is not None:
        body["topic"] = topic
    return body


def build_research_body(
    query: str,
    *,
    deep: bool = False,
    max_sources: int | None = None,
    max_iterations: int | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query, "deep": deep}
    if max_sources is not None:
        body["max_sources"] = max_sources
    if max_iterations is not None:
        body["max_iterations"] = max_iterations
    if topic is not None:
        body["topic"] = topic
    return body


def build_watch_create_body(
    url: str,
    *,
    name: str | None = None,
    interval_minutes: int = 1440,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"url": url, "interval_minutes": interval_minutes}
    if name is not None:
        body["name"] = name
    if webhook_url is not None:
        body["webhook_url"] = webhook_url
    return body


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def parse_scrape(data: dict[str, Any]) -> ScrapeResponse:
    cache = None
    if data.get("cache"):
        cache = CacheInfo(status=data["cache"]["status"])
    return ScrapeResponse(
        url=data["url"],
        metadata=data.get("metadata", {}),
        markdown=data.get("markdown"),
        text=data.get("text"),
        llm=data.get("llm"),
        json_data=data.get("json"),
        cache=cache,
        warning=data.get("warning"),
    )


def parse_crawl_job(data: dict[str, Any]) -> CrawlJob:
    return CrawlJob(id=data["id"], status=data["status"])


def parse_crawl_status(data: dict[str, Any]) -> CrawlStatus:
    pages = [
        CrawlPage(
            url=p["url"],
            markdown=p.get("markdown"),
            metadata=p.get("metadata", {}),
            error=p.get("error"),
        )
        for p in data.get("pages", [])
    ]
    return CrawlStatus(
        id=data["id"],
        status=data["status"],
        pages=pages,
        total=data.get("total", 0),
        completed=data.get("completed", 0),
        errors=data.get("errors", 0),
    )


def parse_map(data: dict[str, Any]) -> MapResponse:
    return MapResponse(urls=data.get("urls", []), count=data.get("count", 0))


def parse_batch(data: dict[str, Any]) -> BatchResponse:
    results = [
        BatchResult(
            url=r["url"],
            markdown=r.get("markdown"),
            metadata=r.get("metadata", {}),
            error=r.get("error"),
        )
        for r in data.get("results", [])
    ]
    return BatchResponse(results=results)


def parse_extract(data: dict[str, Any]) -> ExtractResponse:
    return ExtractResponse(data=data.get("data"))


def parse_summarize(data: dict[str, Any]) -> SummarizeResponse:
    return SummarizeResponse(summary=data.get("summary", ""))


def parse_brand(data: dict[str, Any]) -> BrandResponse:
    return BrandResponse(data=data)


def parse_research(data: dict[str, Any]) -> ResearchStatusResponse:
    return ResearchStatusResponse(
        id=data.get("id", ""),
        status=data.get("status", ""),
        query=data.get("query", ""),
        report=data.get("report", ""),
        sources=data.get("sources", []),
        findings=data.get("findings", []),
        iterations=data.get("iterations", 0),
        elapsed_ms=data.get("elapsed_ms", 0),
    )


def parse_watch_entry(data: dict[str, Any]) -> WatchEntry:
    return WatchEntry.from_dict(data)


def parse_watch_list(data: dict[str, Any]) -> WatchListResponse:
    watches = [WatchEntry.from_dict(w) for w in data.get("watches", [])]
    return WatchListResponse(watches=watches, total=data.get("total", len(watches)))


def parse_watch_check(data: dict[str, Any]) -> WatchCheckResponse:
    return WatchCheckResponse(
        id=data.get("id", ""),
        has_changed=data.get("has_changed", False),
        diff=data.get("diff"),
        checked_at=data.get("checked_at", ""),
    )
