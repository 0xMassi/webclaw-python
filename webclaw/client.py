"""Synchronous Webclaw client."""

from __future__ import annotations

import time
from typing import Any, Sequence
from urllib.parse import quote

import httpx

from . import _endpoints as ep
from .errors import AuthenticationError, NotFoundError, RateLimitError, TimeoutError, WebclawError
from .types import (
    BatchResponse, BrandResponse, CrawlStatus, EndpointsResponse,
    ExtractResponse, LeadBatchJob, LeadBatchStatus, LeadResponse, MapResponse,
    ResearchStatusResponse, ScrapeResponse, SummarizeResponse,
    WatchCheckResponse, WatchEntry, WatchListResponse, XAudienceResponse,
    XMonitor, XMonitorListResponse,
)


class Webclaw:
    """Synchronous client for the Webclaw web extraction API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = ep.DEFAULT_BASE_URL,
        timeout: float = ep.DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Webclaw:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # -- internal -------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Request to {path} timed out") from exc
        except httpx.TransportError as exc:
            raise WebclawError(f"Transport error contacting {path}: {exc}") from exc
        _raise_for_status(response)
        return _decode_json_body(response)

    # -- endpoints ------------------------------------------------------------

    def scrape(
        self,
        url: str,
        *,
        formats: Sequence[str] | None = None,
        include_selectors: list[str] | None = None,
        exclude_selectors: list[str] | None = None,
        only_main_content: bool = False,
        no_cache: bool = False,
    ) -> ScrapeResponse:
        """Scrape a URL and extract content."""
        body = ep.build_scrape_body(
            url, formats=formats, include_selectors=include_selectors,
            exclude_selectors=exclude_selectors, only_main_content=only_main_content,
            no_cache=no_cache,
        )
        return ep.parse_scrape(self._request("POST", "/v1/scrape", json=body))

    def crawl(
        self, url: str, *, max_depth: int = 2, max_pages: int = 50, use_sitemap: bool = False,
    ) -> CrawlJobHandle:
        """Start a crawl job and return a handle for polling."""
        body = ep.build_crawl_body(url, max_depth=max_depth, max_pages=max_pages, use_sitemap=use_sitemap)
        job = ep.parse_crawl_job(self._request("POST", "/v1/crawl", json=body))
        return CrawlJobHandle(client=self, job_id=job.id, status=job.status)

    def get_crawl_status(self, job_id: str) -> CrawlStatus:
        """Get current status of a crawl job."""
        return ep.parse_crawl_status(self._request("GET", f"/v1/crawl/{job_id}"))

    def map(self, url: str) -> MapResponse:
        """Discover URLs from a site's sitemap."""
        return ep.parse_map(self._request("POST", "/v1/map", json={"url": url}))

    def endpoints(
        self,
        url: str,
        *,
        include_third_party: bool = False,
        max_bundles: int = 20,
    ) -> EndpointsResponse:
        """Discover API endpoints embedded in a page's JavaScript.

        Scans inline ``<script>`` blocks and external ``<script src>``
        bundles for the API calls a page makes at runtime -- the routes
        a single-page app hits that :meth:`map` (sitemap-based) cannot
        see. Returns relative paths, absolute URLs, GraphQL operations,
        and WebSocket endpoints.

        :param url: Page URL to analyse.
        :param include_third_party: Also report endpoints whose host is
            not the page's own (analytics, CDNs, etc.). Default False.
        :param max_bundles: Max external script bundles to fetch and
            scan. Server caps this at 20; larger values are clamped.
        """
        body = ep.build_endpoints_body(
            url, include_third_party=include_third_party, max_bundles=max_bundles,
        )
        return ep.parse_endpoints(self._request("POST", "/v1/endpoints", json=body))

    def batch(
        self, urls: list[str], *, formats: Sequence[str] | None = None, concurrency: int = 5,
    ) -> BatchResponse:
        """Scrape multiple URLs in parallel."""
        body = ep.build_batch_body(urls, formats=formats, concurrency=concurrency)
        return ep.parse_batch(self._request("POST", "/v1/batch", json=body))

    def extract(self, url: str, *, schema: dict[str, Any] | None = None, prompt: str | None = None) -> ExtractResponse:
        """LLM-powered structured data extraction."""
        body = ep.build_extract_body(url, schema=schema, prompt=prompt)
        return ep.parse_extract(self._request("POST", "/v1/extract", json=body))

    def lead(self, url: str, *, no_cache: bool = False) -> LeadResponse:
        """Enrich a company from its website into a structured lead.

        Returns the company name, summary, socials, tech stack, pricing,
        emails, and people (each with optional LinkedIn / X profile URLs).

        Flat 100 credits per successful lead.
        """
        body = ep.build_lead_body(url, no_cache=no_cache)
        return ep.parse_lead(self._request("POST", "/v1/lead", json=body))

    def lead_batch(self, urls: list[str], *, no_cache: bool = False) -> LeadBatchJob:
        """Start an async batch lead-enrichment job for 1..25 company URLs.

        Returns immediately with a job id and status ``"processing"``; poll
        :meth:`get_lead_batch` (or block with :meth:`wait_for_lead_batch`)
        until the status is ``"completed"`` or ``"failed"``. The server
        validates the count (400 for zero or more than 25) and dedupes the
        list. Billed 100 credits per *successful* lead -- error results are
        not charged.
        """
        body = ep.build_lead_batch_body(urls, no_cache=no_cache)
        return ep.parse_lead_batch_job(self._request("POST", "/v1/lead/batch", json=body))

    def get_lead_batch(self, job_id: str) -> LeadBatchStatus:
        """Get status/results of a lead batch job without polling."""
        return ep.parse_lead_batch_status(self._request("GET", f"/v1/lead/batch/{job_id}"))

    def wait_for_lead_batch(
        self, job_id: str, *, interval: float = 2.0, timeout: float = 600.0,
    ) -> LeadBatchStatus:
        """Poll an existing lead batch job by id until it completes or fails.

        Mirrors :meth:`wait_for_research` / :meth:`wait_for_crawl`: same
        capped backoff and terminal/unknown-status fail-fast behaviour.
        """
        return _poll_until_done(
            fetcher=lambda: self._request("GET", f"/v1/lead/batch/{job_id}"),
            parser=ep.parse_lead_batch_status,
            label=f"Lead batch {job_id}",
            interval=interval,
            timeout=timeout,
        )

    def summarize(self, url: str, *, max_sentences: int | None = None) -> SummarizeResponse:
        """Summarize page content."""
        return ep.parse_summarize(self._request("POST", "/v1/summarize", json=ep.build_summarize_body(url, max_sentences=max_sentences)))

    def brand(self, url: str) -> BrandResponse:
        """Extract brand identity from a URL."""
        return ep.parse_brand(self._request("POST", "/v1/brand", json={"url": url}))

    def search(self, query: str, *, num_results: int | None = None, topic: str | None = None) -> dict:
        """Run a web search query via the Serper-backed search endpoint."""
        return self._request("POST", "/v1/search", json=ep.build_search_body(query, num_results=num_results, topic=topic))

    def list_extractors(self) -> dict:
        """List all vertical extractors available on the server.

        Returns the catalog as ``{"extractors": [{name, label, description, url_patterns}, ...]}``.
        Use the ``name`` values with :meth:`scrape_vertical` to run a specific parser.
        """
        return self._request("GET", "/v1/extractors")

    def scrape_vertical(self, name: str, url: str) -> dict:
        """Run a vertical extractor by name and return typed JSON.

        Verticals return site-specific structured fields (title, price,
        rating, author, etc.) rather than generic markdown. Call
        :meth:`list_extractors` to see the full catalog of 28 extractors.

        :param name: Vertical extractor name, e.g. ``"reddit"``,
            ``"github_repo"``, ``"trustpilot_reviews"``, ``"youtube_video"``,
            ``"shopify_product"``.
        :param url: URL to extract. Must match the URL patterns the
            extractor claims; the server returns 400 on mismatch.
        :returns: ``{"vertical": str, "url": str, "data": dict}``. The
            ``data`` shape is extractor-specific; the caller should know
            which vertical they invoked and cast accordingly.
        """
        if not name:
            raise ValueError("name is required")
        if not url:
            raise ValueError("url is required")
        # URL-encode the vertical name to be safe against typo'd input,
        # even though legitimate names are always [a-z_].
        return self._request("POST", f"/v1/scrape/{quote(name, safe='')}", json={"url": url})

    def diff(self, url: str, **kwargs: Any) -> dict:
        """Detect content changes at a URL since the last check."""
        return self._request("POST", "/v1/diff", json={"url": url, **kwargs})

    def research(
        self, query: str, *, deep: bool = False,
        max_sources: int | None = None, max_iterations: int | None = None, topic: str | None = None,
    ) -> ResearchStatusResponse:
        """Start a research job and block until it completes.

        Normal queries time out after 600s, deep research after 1200s.
        """
        body = ep.build_research_body(query, deep=deep, max_sources=max_sources, max_iterations=max_iterations, topic=topic)
        job_id = self._request("POST", "/v1/research", json=body)["id"]
        return _poll_until_done(
            fetcher=lambda: self._request("GET", f"/v1/research/{job_id}"),
            parser=ep.parse_research,
            label=f"Research {job_id}",
            interval=2.0,
            timeout=1200.0 if deep else 600.0,
        )

    def get_research_status(self, job_id: str) -> ResearchStatusResponse:
        """Get status/results of a research job without polling."""
        return ep.parse_research(self._request("GET", f"/v1/research/{job_id}"))

    def wait_for_research(
        self, job_id: str, *, interval: float = 2.0, timeout: float = 1200.0,
    ) -> ResearchStatusResponse:
        """Poll an existing research job by id until it completes or fails.

        Mirrors sdk-go's ``WaitForResearch`` and sdk-js's ``waitForResearch``.
        Useful when the job id was persisted from a prior ``research()`` call
        in another process and you want to block-until-done without
        restarting the job.

        Default timeout is 1200s (20 min), matching the deep-research window
        on the server side. Override for shorter waits.
        """
        return _poll_until_done(
            fetcher=lambda: self._request("GET", f"/v1/research/{job_id}"),
            parser=ep.parse_research,
            label=f"Research {job_id}",
            interval=interval,
            timeout=timeout,
        )

    def wait_for_crawl(
        self, job_id: str, *, interval: float = 2.0, timeout: float = 300.0,
    ) -> CrawlStatus:
        """Poll an existing crawl job by id until it completes or fails.

        Same semantics as ``CrawlJobHandle.wait`` but for callers who only
        have the id. Mirrors sdk-go's ``WaitForCompletion``.
        """
        return _poll_until_done(
            fetcher=lambda: self.get_crawl_status(job_id),
            parser=lambda s: s,
            label=f"Crawl {job_id}",
            interval=interval,
            timeout=timeout,
            status_attr="status",
        )

    # -- watch endpoints ------------------------------------------------------

    def watch_create(
        self, url: str, *, name: str | None = None, interval_minutes: int = 1440, webhook_url: str | None = None,
    ) -> WatchEntry:
        """Create a new watch monitor for a URL."""
        body = ep.build_watch_create_body(url, name=name, interval_minutes=interval_minutes, webhook_url=webhook_url)
        return ep.parse_watch_entry(self._request("POST", "/v1/watch", json=body))

    def watch_list(self, *, limit: int = 50, offset: int = 0) -> WatchListResponse:
        """List all watch monitors."""
        return ep.parse_watch_list(self._request("GET", "/v1/watch", params={"limit": limit, "offset": offset}))

    def watch_get(self, watch_id: str) -> WatchEntry:
        """Get a single watch monitor by ID."""
        return ep.parse_watch_entry(self._request("GET", f"/v1/watch/{watch_id}"))

    def watch_delete(self, watch_id: str) -> None:
        """Delete a watch monitor."""
        self._request("DELETE", f"/v1/watch/{watch_id}")

    def watch_check(self, watch_id: str) -> WatchCheckResponse:
        """Trigger an immediate check for a watch monitor."""
        return ep.parse_watch_check(self._request("POST", f"/v1/watch/{watch_id}/check"))

    # -- X (Twitter) monitoring -----------------------------------------------
    #
    # The X analog of the watch endpoints: a monitor polls X on a schedule and
    # fires a webhook on new matches. Paid-only -- the server returns 403 for
    # free/lapsed accounts (surfaced as AuthenticationError). Monitors cost 1
    # credit per check; audience export costs 1 credit per page fetched. Max 50
    # monitors per user.

    def create_x_monitor(
        self,
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
    ) -> XMonitor:
        """Create an X monitor that polls X and fires a webhook on new matches.

        :param kind: One of ``"profile"``, ``"search"``, ``"list"``,
            ``"replies"`` (the values in ``XMonitorKind``).
        :param target: Handle (leading ``@`` is stripped server-side), search
            query, list id, or tweet id -- interpreted per ``kind``.
        :param interval_minutes: Poll cadence; server default 15, clamped
            2..10080. Omit to accept the server default.
        :param webhook_url: Discord/Slack/generic webhook fired on new matches.
        :param min_faves: Minimum likes for a tweet to match (server default 0).
        :param keyword: Only match tweets containing this substring.
        :param lang: Only match tweets in this language code.
        """
        body = ep.build_x_monitor_create_body(
            kind, target, name=name, interval_minutes=interval_minutes,
            webhook_url=webhook_url, include_retweets=include_retweets,
            include_replies=include_replies, include_quotes=include_quotes,
            min_faves=min_faves, keyword=keyword, lang=lang,
        )
        return ep.parse_x_monitor(self._request("POST", ep.X_MONITORS_PATH, json=body))

    def list_x_monitors(self, *, limit: int = 50, offset: int = 0) -> XMonitorListResponse:
        """List X monitors (each a full monitor object)."""
        return ep.parse_x_monitor_list(
            self._request("GET", ep.X_MONITORS_PATH, params={"limit": limit, "offset": offset})
        )

    def get_x_monitor(self, monitor_id: str) -> XMonitor:
        """Get a single X monitor by id (full monitor object)."""
        return ep.parse_x_monitor(self._request("GET", ep.x_monitor_path(monitor_id)))

    def update_x_monitor(
        self,
        monitor_id: str,
        *,
        name: str | None = None,
        interval_minutes: int | None = None,
        webhook_url: str | None = None,
        active: bool | None = None,
    ) -> None:
        """Update an X monitor. Only the fields you pass are changed."""
        body = ep.build_x_monitor_update_body(
            name=name, interval_minutes=interval_minutes,
            webhook_url=webhook_url, active=active,
        )
        self._request("PATCH", ep.x_monitor_path(monitor_id), json=body)

    def delete_x_monitor(self, monitor_id: str) -> None:
        """Delete an X monitor."""
        self._request("DELETE", ep.x_monitor_path(monitor_id))

    def check_x_monitor(self, monitor_id: str) -> None:
        """Trigger an immediate check for an X monitor (runs in the background).

        Returns nothing; the server responds ``{"status": "checking"}`` and
        the actual poll + webhook happen asynchronously. Costs 1 credit.
        """
        self._request("POST", ep.x_monitor_check_path(monitor_id))

    def export_x_audience(
        self,
        *,
        handle: str | None = None,
        user_id: str | None = None,
        direction: str | None = None,
        cursor: str | None = None,
        max_pages: int | None = None,
    ) -> XAudienceResponse:
        """Export an account's followers or following, cursor-paginated.

        Provide ``handle`` OR ``user_id`` (a pre-resolved numeric id skips the
        unbilled re-resolve on later pages). Metered at 1 credit per page.

        :param direction: ``"followers"`` (default) or ``"following"``.
        :param cursor: Opaque ``next_cursor`` from a previous response.
        :param max_pages: Server default 2, clamped 1..10 (~1-2k users/page).

        To page a full audience, call repeatedly, passing the returned
        ``user_id`` and ``next_cursor`` back in, until ``next_cursor`` is
        ``None``.
        """
        body = ep.build_x_audience_body(
            handle=handle, user_id=user_id, direction=direction,
            cursor=cursor, max_pages=max_pages,
        )
        return ep.parse_x_audience(self._request("POST", ep.X_AUDIENCE_PATH, json=body))


class CrawlJobHandle:
    """Wraps a running crawl job with polling helpers."""

    def __init__(self, client: Webclaw, job_id: str, status: str) -> None:
        self.client = client
        self.id = job_id
        self.status = status

    def get_status(self) -> CrawlStatus:
        return self.client.get_crawl_status(self.id)

    def wait(self, *, interval: float = 2.0, timeout: float = 300.0) -> CrawlStatus:
        """Poll until the crawl completes or fails."""
        return _poll_until_done(
            fetcher=self.get_status, parser=lambda s: s,
            label=f"Crawl {self.id}", interval=interval, timeout=timeout,
            status_attr="status",
        )


# -- helpers ------------------------------------------------------------------

def _decode_json_body(response: httpx.Response) -> Any:
    """Decode a successful response body as JSON, tolerating empty bodies.

    A 204 No Content (e.g. watch_delete) or any other success with an empty
    body has nothing to parse -- return None instead of letting
    response.json() raise a JSONDecodeError. A non-empty body that still
    isn't valid JSON is a real server contract violation, so surface it as a
    clear WebclawError rather than a bare decode error.
    """
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise WebclawError(
            f"Expected JSON response but got non-JSON body (status {response.status_code})",
            status_code=response.status_code,
        ) from exc


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    # Parse the body once. A well-formed error is a JSON object with an
    # "error" key, but the server (or an upstream proxy) may return a JSON
    # array, string, number, or non-JSON text on failure -- none of those
    # have .get(), so fall back to the raw text instead of masking the
    # real status with an AttributeError.
    try:
        parsed = response.json()
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        detail = parsed.get("error", response.text)
    else:
        detail = response.text

    if response.status_code in (401, 403):
        raise AuthenticationError(str(detail))
    if response.status_code == 404:
        raise NotFoundError(str(detail))
    if response.status_code == 429:
        raise RateLimitError(str(detail))
    raise WebclawError(str(detail), status_code=response.status_code)


# Backoff ceiling for poll loops: the per-request delay grows from
# `interval` up to this cap so a long-running job does not hammer the API
# every `interval` seconds for its entire (up to 20 min) lifetime.
_POLL_MAX_INTERVAL = 15.0
_POLL_BACKOFF_FACTOR = 1.5

# How many *consecutive* transient fetch failures the poll loop tolerates
# before giving up. A flaky network blip or a brief 429/5xx mid-job
# shouldn't abort a 20-minute research job; a sustained outage still bails.
# Mirrors the JS SDK's isTransientPollError cap.
_MAX_TRANSIENT_POLL_FAILURES = 5


def _is_transient_poll_error(exc: Exception) -> bool:
    """Whether a fetch error during polling is worth retrying.

    Rate limits, timeouts, and 5xx WebclawErrors are transient: the job is
    still running server-side, the status fetch just failed. Auth/404 and
    other 4xx are terminal and re-raised immediately.
    """
    if isinstance(exc, (TimeoutError, RateLimitError)):
        return True
    if isinstance(exc, WebclawError):
        code = exc.status_code
        return code is not None and 500 <= code < 600
    return False


def _classify_status(result: Any, status_attr: str) -> str:
    return result.get("status", "") if isinstance(result, dict) else getattr(result, status_attr, "")


def _poll_outcome(result: Any, status: str, parser, label: str) -> Any:
    """Return parser(result) on success, raise on a terminal failure or an
    unrecognised (assumed-terminal) status, or return the sentinel
    ``_KEEP_POLLING`` while the job is still in flight."""
    if status == ep.SUCCESS_STATE:
        return parser(result)
    if status in ep.FAILURE_STATES:
        error = result.get("error", f"{label} failed") if isinstance(result, dict) else f"{label} failed"
        raise WebclawError(error or f"{label} failed", status_code=None)
    if status not in ep.IN_PROGRESS_STATES:
        # Unknown status: treat as terminal so we fail fast instead of
        # looping until the wall-clock timeout on a status the server
        # added that this SDK version does not understand.
        raise WebclawError(f"{label} returned unknown status {status!r}", status_code=None)
    return _KEEP_POLLING


_KEEP_POLLING = object()


def _poll_until_done(
    *, fetcher, parser, label: str, interval: float, timeout: float, status_attr: str = "status",
) -> Any:
    """Poll fetcher() until terminal state, then return parser(result).

    For research: fetcher returns raw dict, parser converts to dataclass.
    For crawl: fetcher returns CrawlStatus, parser is identity.

    The delay between polls starts at ``interval`` and grows by
    ``_POLL_BACKOFF_FACTOR`` up to ``_POLL_MAX_INTERVAL``. A terminal
    failure or an unrecognised status raises immediately rather than
    waiting out ``timeout``.
    """
    deadline = time.monotonic() + timeout
    delay = interval
    transient_failures = 0
    while True:
        try:
            result = fetcher()
        except WebclawError as exc:
            if not _is_transient_poll_error(exc):
                raise
            transient_failures += 1
            if transient_failures > _MAX_TRANSIENT_POLL_FAILURES:
                raise WebclawError(
                    f"{label} polling gave up after {_MAX_TRANSIENT_POLL_FAILURES} "
                    f"consecutive transient failures: {exc}",
                    status_code=exc.status_code,
                ) from exc
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{label} did not complete within {timeout}s") from exc
            time.sleep(delay)
            delay = min(delay * _POLL_BACKOFF_FACTOR, _POLL_MAX_INTERVAL)
            continue
        transient_failures = 0
        status = _classify_status(result, status_attr)
        outcome = _poll_outcome(result, status, parser, label)
        if outcome is not _KEEP_POLLING:
            return outcome
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{label} did not complete within {timeout}s")
        time.sleep(delay)
        delay = min(delay * _POLL_BACKOFF_FACTOR, _POLL_MAX_INTERVAL)
