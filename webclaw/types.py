"""Response types for the Webclaw API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# -- Scrape ------------------------------------------------------------------

@dataclass
class CacheInfo:
    status: str  # "hit" | "miss" | "bypass"


@dataclass
class YouTubeData:
    """Structured YouTube metadata returned by `/v1/scrape` for any
    `youtube.com/watch`, `youtube.com/shorts`, or `youtu.be/` URL.

    Populated via the server's yt-dlp short-circuit (preferred) or the
    standard pipeline's vertical YouTube extractor (transcript will be
    `None` on this fallback path)."""
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
    cache: CacheInfo | None = None
    warning: str | None = None
    # YouTube-only — set when the URL is a YouTube watch/shorts/youtu.be.
    youtube: YouTubeData | None = None
    # Auto-caption transcript text (newline-joined). Only present when the
    # yt-dlp short-circuit fired and the video has captions.
    transcript: str | None = None


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


# -- Lead --------------------------------------------------------------------
#
# `/v1/lead` enriches a company from its website into a structured lead:
# company name, summary, socials, tech stack, pricing, emails, and people.
# Flat 100 credits per successful lead.

@dataclass
class LeadSocials:
    """Social profile URLs discovered for the company."""
    linkedin: str | None = None
    x: str | None = None
    github: str | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LeadSocials:
        return LeadSocials(
            linkedin=data.get("linkedin"),
            x=data.get("x"),
            github=data.get("github"),
        )


@dataclass
class LeadPricingPlan:
    """A single pricing plan and its price string."""
    plan: str = ""
    price: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LeadPricingPlan:
        return LeadPricingPlan(
            plan=data.get("plan", ""),
            price=data.get("price", ""),
        )


@dataclass
class LeadEmail:
    """A discovered contact email, tagged by its role (e.g. "support")."""
    type: str = ""
    email: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LeadEmail:
        return LeadEmail(
            type=data.get("type", ""),
            email=data.get("email", ""),
        )


@dataclass
class LeadPerson:
    """A person associated with the company: name, role, and optional
    LinkedIn / X profile URLs (either may be absent)."""
    name: str = ""
    role: str = ""
    linkedin: str | None = None
    x: str | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LeadPerson:
        return LeadPerson(
            name=data.get("name", ""),
            role=data.get("role", ""),
            linkedin=data.get("linkedin"),
            x=data.get("x"),
        )


@dataclass
class LeadData:
    """The enriched company profile inside a LeadResponse."""
    company_name: str | None = None
    summary: str | None = None
    socials: LeadSocials = field(default_factory=LeadSocials)
    tech: list[str] = field(default_factory=list)
    pricing: list[LeadPricingPlan] = field(default_factory=list)
    emails: list[LeadEmail] = field(default_factory=list)
    people: list[LeadPerson] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LeadData:
        raw_socials = data.get("socials")
        socials = LeadSocials.from_dict(raw_socials if isinstance(raw_socials, dict) else {})
        pricing = [
            LeadPricingPlan.from_dict(p) for p in data.get("pricing", []) if isinstance(p, dict)
        ]
        emails = [
            LeadEmail.from_dict(e) for e in data.get("emails", []) if isinstance(e, dict)
        ]
        people = [
            LeadPerson.from_dict(p) for p in data.get("people", []) if isinstance(p, dict)
        ]
        return LeadData(
            company_name=data.get("company_name"),
            summary=data.get("summary"),
            socials=socials,
            tech=list(data.get("tech") or []),
            pricing=pricing,
            emails=emails,
            people=people,
        )


@dataclass
class LeadResponse:
    """Company enrichment from `/v1/lead`. Flat 100 credits per successful lead."""
    url: str = ""
    domain: str = ""
    lead: LeadData = field(default_factory=LeadData)
    people_source: str = ""
    cache: str = ""  # "hit" | "miss"
    credits: int = 0


# -- Lead batch --------------------------------------------------------------
#
# `/v1/lead/batch` enriches 1..25 company websites in one ASYNC job. POST
# returns immediately with a job id; poll `GET /v1/lead/batch/{id}` until the
# status is "completed" or "failed". 100 credits per *successful* lead --
# error results are not billed.

@dataclass
class LeadBatchJob:
    """Returned immediately when a lead batch job is started."""
    id: str = ""
    status: str = ""  # "processing"
    total: int = 0
    credits_per_url: int = 0


@dataclass
class LeadBatchResult:
    """One URL's outcome inside a LeadBatchStatus.

    On success `status == "success"` and `domain` / `lead` / `cache` are
    populated (`lead` is the same enriched profile `LeadResponse.lead`
    carries). On failure `status == "error"` and `error` holds the reason
    while `lead` is None."""
    url: str = ""
    status: str = ""  # "success" | "error"
    domain: str = ""
    lead: LeadData | None = None
    cache: str = ""  # "hit" | "miss"
    error: str | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LeadBatchResult:
        raw_lead = data.get("lead")
        lead = LeadData.from_dict(raw_lead) if isinstance(raw_lead, dict) else None
        return LeadBatchResult(
            url=data.get("url", ""),
            status=data.get("status", ""),
            domain=data.get("domain", ""),
            lead=lead,
            cache=data.get("cache", ""),
            error=data.get("error"),
        )


@dataclass
class LeadBatchStatus:
    """Full lead batch job status including per-URL results. `credits_charged`
    reflects only the successful leads (100 credits each)."""
    id: str = ""
    status: str = ""  # "processing" | "completed" | "failed"
    total: int = 0
    completed: int = 0
    succeeded: int = 0
    credits_charged: int = 0
    results: list[LeadBatchResult] = field(default_factory=list)
    error: str | None = None
    created_at: str = ""


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
#
# `Webclaw.search()` and `Webclaw.diff()` return the raw server JSON as a
# `dict`. Typed wrappers used to be exported here but were never produced
# by any client method, so they advertised a contract the SDK did not
# honour. They were removed; typing these endpoints is a deliberate
# public-API change, not an accidental one.


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
