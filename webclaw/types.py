"""Response types for the Webclaw API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


# -- Scrape ------------------------------------------------------------------

@dataclass
class CacheInfo:
    status: str  # "hit" | "miss" | "bypass" | "skip"
    cached_at: str | None = None
    age_seconds: int | None = None


@dataclass
class YouTubeData:
    """Structured YouTube metadata returned by `/v1/scrape` for any
    `youtube.com/watch`, `youtube.com/shorts`, or `youtu.be/` URL.

    Metadata may be returned without captions; inspect `warning` and
    `transcript` on the scrape response before treating it as a transcript."""
    video_id: str | None = None
    title: str | None = None
    description: str | None = None
    channel: str | None = None
    channel_url: str | None = None
    uploader: str | None = None
    upload_date: str | None = None  # YYYYMMDD
    duration_seconds: int | None = None
    view_count: int | None = None
    like_count: int | None = None
    thumbnail: str | None = None
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    language: str | None = None


@dataclass
class ScrapeResponse:
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    markdown: str | None = None
    text: str | None = None
    llm: str | None = None
    json_data: Any | None = None
    extract: Any | None = None
    cache: CacheInfo | None = None
    warning: str | None = None
    # YouTube-only — set when the URL is a YouTube watch/shorts/youtu.be.
    youtube: YouTubeData | None = None
    # Auto-caption transcript text (newline-joined). Only present when the
    # yt-dlp short-circuit fired and the video has captions.
    transcript: str | None = None


    links: list[dict[str, Any]] | None = None
    raw_html: str | None = None
    attributes: list[dict[str, Any]] | None = None
    query_answer: str | None = None
    screenshot: str | None = None
    actions_performed: int | None = None
    mobile: bool | None = None
    structured_data: Any | None = None
    engine: dict[str, Any] | None = None


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
    next_cursor: str | None = None
    total_indexed: int | None = None
    cached: bool | None = None
    urls: list[str] = field(default_factory=list)
    count: int = 0


# -- Batch -------------------------------------------------------------------

@dataclass
class BatchResult:
    url: str
    markdown: str | None = None
    text: str | None = None
    llm: str | None = None
    json_data: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # Present only when a YouTube URL is batched and the server returns the
    # yt-dlp short-circuit shape; None for ordinary pages.
    youtube: YouTubeData | None = None
    transcript: str | None = None


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


# -- Search / Diff -----------------------------------------------------------

SearchFreshness = Literal["hour", "day", "week", "month", "year"]


class SearchAppliedFilters(TypedDict, total=False):
    """Non-default source filters and provider discovery hints.

    Fields are optional so the SDK remains compatible with older hosted and
    self-hosted servers while the additive response contract rolls out.
    """

    include_domains: list[str]
    exclude_domains: list[str]
    include_url_prefixes: list[str]
    freshness: SearchFreshness
    published_after: str
    published_before: str
    location: str
    autocorrect: bool


class SearchResponse(TypedDict, total=False):
    """Raw JSON returned by :meth:`Webclaw.search`."""

    query: str
    results: list[dict[str, Any]]
    scrape: bool
    applied_filters: SearchAppliedFilters
    filtered_out_count: int
    page: int


# `Webclaw.diff()` still returns the raw server JSON as a `dict`. Its old
# dataclass wrapper was never produced by the client and remains removed.


# -- Research ----------------------------------------------------------------
#
# `research()` blocks and returns `ResearchStatusResponse`. The transient
# start payload (`{id, status}`) is consumed internally as a dict, and
# `sources` / `findings` are passed through as `list[dict]`, so the
# previously-exported ResearchStartResponse / ResearchFinding /
# ResearchSource wrappers were dead and have been removed.

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


    sources_count: int | None = None
    findings_count: int | None = None
    total_pages_analyzed: int | None = None
    created_at: str | None = None
    error: str | None = None


# -- Watch -------------------------------------------------------------------

@dataclass
class WatchEntry:
    """A saved monitor; create responses may omit check timestamps."""
    id: str = ""
    url: str = ""
    name: str | None = None
    interval_minutes: int = 1440
    webhook_url: str | None = None
    active: bool = False
    last_checked_at: str | None = None
    last_changed_at: str | None = None
    created_at: str | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> WatchEntry:
        return WatchEntry(**{key: value for key, value in data.items() if key in WatchEntry.__dataclass_fields__})


@dataclass
class WatchSnapshot:
    id: str = ""
    content_hash: str = ""
    word_count: int = 0
    status: str = ""
    title: str | None = None
    diff_summary: str | None = None
    word_count_delta: int = 0
    links_added: int = 0
    links_removed: int = 0
    checked_at: str = ""


@dataclass
class WatchDetail(WatchEntry):
    snapshots: list[WatchSnapshot] = field(default_factory=list)


@dataclass
class WatchListResponse:
    watches: list[WatchEntry] = field(default_factory=list)
    # Older servers may supply a total. Page length is not a total.
    total: int | None = None


@dataclass
class WatchCheckResponse:
    """Acknowledges an async check; read watch_get() for the saved snapshots."""
    status: str


# -- X (Twitter) monitoring --------------------------------------------------
#
# The X monitoring endpoints are the X analog of the URL-monitoring `watch`
# endpoints: a monitor polls X on a schedule and fires a webhook on new
# matches. These are paid-only features -- the server returns 403 for
# free/lapsed accounts. Monitors cost 1 credit per check (automated or
# manual); audience export costs 1 credit per page fetched.

# The four monitor kinds the server accepts. Kept as a tuple of the literal
# strings so callers can branch on `monitor.kind` without importing an enum;
# an unknown future kind passes through unchanged as a plain string.
XMonitorKind = ("profile", "search", "list", "replies")


@dataclass
class XMonitor:
    """A single X (Twitter) monitor.

    A create/get/list response is the same object; `list`/`get` return the
    full set of fields, while the `create` response populates only the core
    subset (id, kind, target, name, interval_minutes, webhook_url, active).
    The remaining match-filter and timestamp fields default sensibly so a
    partial create payload still parses.
    """
    id: str = ""
    kind: str = ""  # one of XMonitorKind
    target: str = ""
    name: str | None = None
    interval_minutes: int = 15
    webhook_url: str | None = None
    active: bool = True
    include_retweets: bool = True
    include_replies: bool = True
    include_quotes: bool = True
    min_faves: int = 0
    keyword: str | None = None
    lang: str | None = None
    last_checked_at: str | None = None
    last_matched_at: str | None = None
    created_at: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> XMonitor:
        return XMonitor(
            id=data.get("id", ""),
            kind=data.get("kind", ""),
            target=data.get("target", ""),
            name=data.get("name"),
            interval_minutes=data.get("interval_minutes", 15),
            webhook_url=data.get("webhook_url"),
            active=data.get("active", True),
            include_retweets=data.get("include_retweets", True),
            include_replies=data.get("include_replies", True),
            include_quotes=data.get("include_quotes", True),
            min_faves=data.get("min_faves", 0),
            keyword=data.get("keyword"),
            lang=data.get("lang"),
            last_checked_at=data.get("last_checked_at"),
            last_matched_at=data.get("last_matched_at"),
            created_at=data.get("created_at", ""),
        )


@dataclass
class XMonitorListResponse:
    monitors: list[XMonitor] = field(default_factory=list)


@dataclass
class XAudienceUser:
    """A single follower/following account in an audience export page."""
    id: str = ""
    screen_name: str = ""
    name: str = ""
    followers: int = 0
    description: str | None = None
    url: str | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> XAudienceUser:
        return XAudienceUser(
            id=data.get("id", ""),
            screen_name=data.get("screen_name", ""),
            name=data.get("name", ""),
            followers=data.get("followers", 0),
            description=data.get("description"),
            url=data.get("url"),
        )


@dataclass
class XAudienceResponse:
    """One cursor-paginated page of an audience export.

    `next_cursor` is `None` once the audience is fully walked. To page a full
    audience, call `x_audience` repeatedly, passing the returned `user_id` and
    `next_cursor` back in, until `next_cursor` is `None`.
    """
    user_id: str = ""
    direction: str = "followers"
    count: int = 0
    users: list[XAudienceUser] = field(default_factory=list)
    next_cursor: str | None = None
    pages_fetched: int = 0
    credits_charged: int = 0


# -- Endpoints ---------------------------------------------------------------
#
# `/v1/endpoints` discovers API endpoints embedded in a page's inline
# JavaScript and `<script src>` bundles -- the calls a SPA makes at
# runtime that `/v1/map` (sitemap-based) can't see.

# The four endpoint kinds the server classifies. Kept as a tuple of the
# literal strings the API returns so callers can branch on
# `endpoint.kind` without importing an enum; unknown future kinds pass
# through unchanged as plain strings.
EndpointKind = ("relative_path", "absolute_url", "graph_ql", "web_socket")


@dataclass
class DiscoveredEndpoint:
    """A single API endpoint found in page JavaScript."""
    value: str = ""
    # One of EndpointKind; treated as an open string so a server-added
    # kind does not break older SDKs.
    kind: str = ""
    first_party: bool = False
    source: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DiscoveredEndpoint:
        return DiscoveredEndpoint(
            value=data.get("value", ""),
            kind=data.get("kind", ""),
            first_party=data.get("first_party", False),
            source=data.get("source", ""),
        )


@dataclass
class EndpointsResponse:
    """API endpoints discovered in a page's inline JS + script bundles."""
    url: str = ""
    bundles_scanned: int = 0
    endpoint_count: int = 0
    endpoints: list[DiscoveredEndpoint] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    truncated: bool = False
