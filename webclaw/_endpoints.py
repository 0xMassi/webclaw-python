"""Shared request body builders and response parsers.

Both sync and async clients delegate to these functions so endpoint
logic lives in exactly one place.  Only the transport layer (sync
httpx vs async httpx) differs between the two clients.
"""

from __future__ import annotations

from typing import Any, Sequence

from .errors import WebclawError
from .types import (
    BatchResponse,
    BatchResult,
    BrandResponse,
    CacheInfo,
    CrawlJob,
    CrawlPage,
    CrawlStatus,
    DiscoveredEndpoint,
    EndpointsResponse,
    ExtractResponse,
    LeadBatchJob,
    LeadBatchResult,
    LeadBatchStatus,
    LeadData,
    LeadResponse,
    MapResponse,
    ResearchStatusResponse,
    ScrapeResponse,
    SummarizeResponse,
    WatchCheckResponse,
    WatchEntry,
    WatchListResponse,
    XAudienceResponse,
    XAudienceUser,
    XMonitor,
    XMonitorListResponse,
    YouTubeData,
)

DEFAULT_BASE_URL = "https://api.webclaw.io"
DEFAULT_TIMEOUT = 30.0

# X (Twitter) monitoring paths. Collected here so the two clients share one
# spelling of every route -- mirrors how the watch endpoints are wired.
X_MONITORS_PATH = "/v1/x/monitors"
X_AUDIENCE_PATH = "/v1/x/audience"


def x_monitor_path(monitor_id: str) -> str:
    return f"{X_MONITORS_PATH}/{monitor_id}"


def x_monitor_check_path(monitor_id: str) -> str:
    return f"{X_MONITORS_PATH}/{monitor_id}/check"

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


def build_lead_body(
    url: str,
    *,
    no_cache: bool = False,
) -> dict[str, Any]:
    # `no_cache` is omitted at its default, mirroring build_scrape_body.
    body: dict[str, Any] = {"url": url}
    if no_cache:
        body["no_cache"] = True
    return body


def build_lead_batch_body(
    urls: list[str],
    *,
    no_cache: bool = False,
) -> dict[str, Any]:
    # `no_cache` is omitted at its default, mirroring build_lead_body. The
    # server validates the 1..25 count and dedupes, so the SDK sends urls
    # through unchanged.
    body: dict[str, Any] = {"urls": urls}
    if no_cache:
        body["no_cache"] = True
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
    # `deep` is deprecated: the server runs every research job in deep mode
    # and ignores the field. Only forward it when a caller explicitly opts
    # in (truthy) so default requests stop carrying a dead field, while an
    # older self-hosted server that still honors it keeps working.
    body: dict[str, Any] = {"query": query}
    if deep:
        body["deep"] = True
    if max_sources is not None:
        body["max_sources"] = max_sources
    if max_iterations is not None:
        body["max_iterations"] = max_iterations
    if topic is not None:
        body["topic"] = topic
    return body


def build_endpoints_body(
    url: str,
    *,
    include_third_party: bool = False,
    max_bundles: int = 20,
) -> dict[str, Any]:
    # The server caps max_bundles at 20 and rejects more with a 400.
    # Clamp here so a caller passing a larger number gets the max scan
    # instead of a hard error.
    body: dict[str, Any] = {"url": url}
    if include_third_party:
        body["include_third_party"] = True
    if max_bundles != 20:
        body["max_bundles"] = min(max_bundles, 20)
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


def build_x_monitor_create_body(
    kind: str,
    target: str,
    *,
    name: str | None = None,
    interval_minutes: int | None = None,
    webhook_url: str | None = None,
    include_retweets: bool | None = None,
    include_replies: bool | None = None,
    include_quotes: bool | None = None,
    min_faves: int | None = None,
    keyword: str | None = None,
    lang: str | None = None,
) -> dict[str, Any]:
    # `kind` and `target` are the only required fields; every filter is
    # omitted when left at its Python default (None) so the server applies
    # its own default rather than the SDK second-guessing it. `interval_minutes`
    # is likewise server-defaulted (15, clamped 2..10080) when not passed.
    body: dict[str, Any] = {"kind": kind, "target": target}
    if name is not None:
        body["name"] = name
    if interval_minutes is not None:
        body["interval_minutes"] = interval_minutes
    if webhook_url is not None:
        body["webhook_url"] = webhook_url
    if include_retweets is not None:
        body["include_retweets"] = include_retweets
    if include_replies is not None:
        body["include_replies"] = include_replies
    if include_quotes is not None:
        body["include_quotes"] = include_quotes
    if min_faves is not None:
        body["min_faves"] = min_faves
    if keyword is not None:
        body["keyword"] = keyword
    if lang is not None:
        body["lang"] = lang
    return body


def build_x_monitor_update_body(
    *,
    name: str | None = None,
    interval_minutes: int | None = None,
    webhook_url: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    # PATCH is a partial update: only send the fields the caller actually set.
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if interval_minutes is not None:
        body["interval_minutes"] = interval_minutes
    if webhook_url is not None:
        body["webhook_url"] = webhook_url
    if active is not None:
        body["active"] = active
    return body


def build_x_audience_body(
    *,
    handle: str | None = None,
    user_id: str | None = None,
    direction: str | None = None,
    cursor: str | None = None,
    max_pages: int | None = None,
) -> dict[str, Any]:
    # Every field is optional server-side; `handle` OR `user_id` identifies
    # the account (user_id skips the unbilled re-resolve on later pages).
    body: dict[str, Any] = {}
    if handle is not None:
        body["handle"] = handle
    if user_id is not None:
        body["user_id"] = user_id
    if direction is not None:
        body["direction"] = direction
    if cursor is not None:
        body["cursor"] = cursor
    if max_pages is not None:
        body["max_pages"] = max_pages
    return body


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def _require(data: dict[str, Any], key: str, *, context: str) -> Any:
    """Pull a required field from a 200 body, raising a clear WebclawError if
    it's missing. A malformed-but-successful response should surface as an
    actionable SDK error, not a bare KeyError from deep in a parser."""
    if key not in data:
        raise WebclawError(f"Malformed {context} response: missing {key!r}")
    return data[key]


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
    raw_cache = data.get("cache")
    if isinstance(raw_cache, dict):
        cache = CacheInfo(status=raw_cache.get("status", ""))
    youtube = _parse_youtube(data.get("youtube"))
    return ScrapeResponse(
        url=_require(data, "url", context="scrape"),
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
    return CrawlJob(
        id=_require(data, "id", context="crawl job"),
        status=_require(data, "status", context="crawl job"),
    )


def parse_crawl_status(data: dict[str, Any]) -> CrawlStatus:
    pages = [
        CrawlPage(
            url=_require(p, "url", context="crawl page"),
            markdown=p.get("markdown"),
            metadata=p.get("metadata", {}),
            error=p.get("error"),
        )
        for p in data.get("pages", [])
    ]
    return CrawlStatus(
        id=_require(data, "id", context="crawl status"),
        status=_require(data, "status", context="crawl status"),
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


def parse_lead(data: dict[str, Any]) -> LeadResponse:
    raw_lead = data.get("lead")
    lead = LeadData.from_dict(raw_lead if isinstance(raw_lead, dict) else {})
    return LeadResponse(
        url=data.get("url", ""),
        domain=data.get("domain", ""),
        lead=lead,
        people_source=data.get("people_source", ""),
        cache=data.get("cache", ""),
        credits=data.get("credits", 0),
    )


def parse_lead_batch_job(data: dict[str, Any]) -> LeadBatchJob:
    return LeadBatchJob(
        id=_require(data, "id", context="lead batch job"),
        status=_require(data, "status", context="lead batch job"),
        total=data.get("total", 0),
        credits_per_url=data.get("credits_per_url", 0),
    )


def parse_lead_batch_status(data: dict[str, Any]) -> LeadBatchStatus:
    results = [
        LeadBatchResult.from_dict(r) for r in data.get("results", []) if isinstance(r, dict)
    ]
    return LeadBatchStatus(
        id=_require(data, "id", context="lead batch status"),
        status=_require(data, "status", context="lead batch status"),
        total=data.get("total", 0),
        completed=data.get("completed", 0),
        succeeded=data.get("succeeded", 0),
        credits_charged=data.get("credits_charged", 0),
        results=results,
        error=data.get("error"),
        created_at=data.get("created_at", ""),
    )


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


def parse_endpoints(data: dict[str, Any]) -> EndpointsResponse:
    endpoints = [
        DiscoveredEndpoint.from_dict(e)
        for e in data.get("endpoints", [])
        if isinstance(e, dict)
    ]
    return EndpointsResponse(
        url=data.get("url", ""),
        bundles_scanned=data.get("bundles_scanned", 0),
        endpoint_count=data.get("endpoint_count", len(endpoints)),
        endpoints=endpoints,
        hosts=data.get("hosts", []),
        truncated=data.get("truncated", False),
    )


def parse_watch_check(data: dict[str, Any]) -> WatchCheckResponse:
    return WatchCheckResponse(
        id=data.get("id", ""),
        has_changed=data.get("has_changed", False),
        diff=data.get("diff"),
        checked_at=data.get("checked_at", ""),
    )


def parse_x_monitor(data: dict[str, Any]) -> XMonitor:
    return XMonitor.from_dict(data)


def parse_x_monitor_list(data: dict[str, Any]) -> XMonitorListResponse:
    monitors = [
        XMonitor.from_dict(m) for m in data.get("monitors", []) if isinstance(m, dict)
    ]
    return XMonitorListResponse(monitors=monitors)


def parse_x_audience(data: dict[str, Any]) -> XAudienceResponse:
    users = [
        XAudienceUser.from_dict(u) for u in data.get("users", []) if isinstance(u, dict)
    ]
    return XAudienceResponse(
        user_id=data.get("user_id", ""),
        direction=data.get("direction", "followers"),
        count=data.get("count", len(users)),
        users=users,
        # next_cursor is explicitly nullable: null means the audience is fully
        # walked, so default to None (not "") to preserve that signal.
        next_cursor=data.get("next_cursor"),
        pages_fetched=data.get("pages_fetched", 0),
        credits_charged=data.get("credits_charged", 0),
    )
