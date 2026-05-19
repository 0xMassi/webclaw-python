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
    YouTubeData,
)

DEFAULT_BASE_URL = "https://api.webclaw.io"
DEFAULT_TIMEOUT = 30.0

# Job lifecycle states shared by crawl and research polling.
#
# The server uses a small, fixed status vocabulary:
#   - crawl jobs:    pending | running | completed | failed | interrupted
#   - research jobs: processing | completed | failed
#
# SUCCESS_STATE is the only state that yields a parsed result. Everything
# else is either still-in-flight (keep polling) or a terminal failure
# (fail fast). A status outside *all* of these sets is treated as an
# unknown terminal state and fails fast too, so an unrecognised
# server-side status can never spin the poll loop until the wall-clock
# timeout.
SUCCESS_STATE = "completed"
FAILURE_STATES = frozenset({"failed", "interrupted", "error", "cancelled", "canceled"})
IN_PROGRESS_STATES = frozenset(
    {"pending", "running", "processing", "queued", "in_progress", "started", ""}
)
# Terminal = anything that is not still in progress. Kept as a single
# name for callers that just need the "is this done" predicate.
TERMINAL_STATES = frozenset({SUCCESS_STATE}) | FAILURE_STATES


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

def _parse_youtube(raw_yt: Any) -> YouTubeData | None:
    """Build a YouTubeData from the server's `youtube` block, or None when
    the block is absent / not an object. Shared by scrape and batch."""
    if not isinstance(raw_yt, dict):
        return None
    return YouTubeData(
        video_id=raw_yt.get("video_id"),
        title=raw_yt.get("title"),
        description=raw_yt.get("description"),
        channel=raw_yt.get("channel"),
        channel_url=raw_yt.get("channel_url"),
        uploader=raw_yt.get("uploader"),
        upload_date=raw_yt.get("upload_date"),
        duration_seconds=raw_yt.get("duration_seconds"),
        view_count=raw_yt.get("view_count"),
        like_count=raw_yt.get("like_count"),
        thumbnail=raw_yt.get("thumbnail"),
        tags=list(raw_yt.get("tags") or []),
        categories=list(raw_yt.get("categories") or []),
        language=raw_yt.get("language"),
    )


def parse_scrape(data: dict[str, Any]) -> ScrapeResponse:
    cache = None
    if data.get("cache"):
        cache = CacheInfo(status=data["cache"]["status"])
    youtube = _parse_youtube(data.get("youtube"))
    return ScrapeResponse(
        url=data["url"],
        metadata=data.get("metadata", {}),
        markdown=data.get("markdown"),
        text=data.get("text"),
        llm=data.get("llm"),
        json_data=data.get("json"),
        cache=cache,
        warning=data.get("warning"),
        youtube=youtube,
        transcript=data.get("transcript"),
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
            text=r.get("text"),
            llm=r.get("llm"),
            # The server keys the json/structured payload as "extraction"
            # in batch entries; accept "json" too for forward-compat.
            json_data=r.get("json", r.get("extraction")),
            metadata=r.get("metadata", {}),
            error=r.get("error"),
            youtube=_parse_youtube(r.get("youtube")),
            transcript=r.get("transcript"),
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
