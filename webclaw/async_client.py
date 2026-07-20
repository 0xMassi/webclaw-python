"""Asynchronous Webclaw client."""

from __future__ import annotations

import asyncio
import time
import warnings
from typing import Any, Sequence
from urllib.parse import quote

import httpx

from . import _endpoints as ep
from .client import (
    _KEEP_POLLING,
    _MAX_TRANSIENT_POLL_FAILURES,
    _POLL_BACKOFF_FACTOR,
    _POLL_MAX_INTERVAL,
    _classify_status,
    _decode_json_body,
    _is_transient_poll_error,
    _poll_outcome,
    _raise_for_status,
)
from .errors import TimeoutError, WebclawError
from .types import (
    BatchResponse, BrandResponse, CrawlStatus, EndpointsResponse,
    ExtractResponse, LeadBatchJob, LeadBatchStatus, LeadResponse, MapResponse,
    ResearchStatusResponse, ScrapeResponse, SummarizeResponse,
    WatchCheckResponse, WatchEntry, WatchListResponse, XAudienceResponse,
    XMonitor, XMonitorListResponse,
)


class AsyncWebclaw:
    """Async client for the Webclaw web extraction API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = ep.DEFAULT_BASE_URL,
        timeout: float = ep.DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    # -- lifecycle ------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncWebclaw:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # -- internal -------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Request to {path} timed out") from exc
        except httpx.TransportError as exc:
            raise WebclawError(f"Transport error contacting {path}: {exc}") from exc
        _raise_for_status(response)
        return _decode_json_body(response)

    # -- endpoints ------------------------------------------------------------

    async def scrape(
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
        return ep.parse_scrape(await self._request("POST", "/v1/scrape", json=body))

    async def crawl(
        self, url: str, *, max_depth: int = 2, max_pages: int = 50, use_sitemap: bool = False,
    ) -> AsyncCrawlJobHandle:
        """Start a crawl job and return a handle for polling."""
        body = ep.build_crawl_body(url, max_depth=max_depth, max_pages=max_pages, use_sitemap=use_sitemap)
        job = ep.parse_crawl_job(await self._request("POST", "/v1/crawl", json=body))
        return AsyncCrawlJobHandle(client=self, job_id=job.id, status=job.status)

    async def get_crawl_status(self, job_id: str) -> CrawlStatus:
        """Get current status of a crawl job."""
        return ep.parse_crawl_status(await self._request("GET", f"/v1/crawl/{job_id}"))

    async def map(self, url: str) -> MapResponse:
        """Discover URLs from a site's sitemap."""
        return ep.parse_map(await self._request("POST", "/v1/map", json={"url": url}))

    async def endpoints(
        self,
        url: str,
        *,
        include_third_party: bool = False,
        max_bundles: int = 20,
    ) -> EndpointsResponse:
        """Async mirror of :meth:`Webclaw.endpoints`.

        Discovers API endpoints embedded in a page's inline JS and
        external script bundles -- the runtime routes a single-page app
        hits that :meth:`map` (sitemap-based) cannot see.
        """
        body = ep.build_endpoints_body(
            url, include_third_party=include_third_party, max_bundles=max_bundles,
        )
        return ep.parse_endpoints(await self._request("POST", "/v1/endpoints", json=body))

    async def batch(
        self, urls: list[str], *, formats: Sequence[str] | None = None, concurrency: int = 5,
    ) -> BatchResponse:
        """Scrape multiple URLs in parallel."""
        body = ep.build_batch_body(urls, formats=formats, concurrency=concurrency)
        return ep.parse_batch(await self._request("POST", "/v1/batch", json=body))

    async def extract(self, url: str, *, schema: dict[str, Any] | None = None, prompt: str | None = None) -> ExtractResponse:
        """LLM-powered structured data extraction."""
        body = ep.build_extract_body(url, schema=schema, prompt=prompt)
        return ep.parse_extract(await self._request("POST", "/v1/extract", json=body))

    async def lead(self, url: str, *, no_cache: bool = False) -> LeadResponse:
        """Enrich a company from its website into a structured lead.

        Async mirror of :meth:`Webclaw.lead`. Flat 100 credits per successful
        lead.
        """
        body = ep.build_lead_body(url, no_cache=no_cache)
        return ep.parse_lead(await self._request("POST", "/v1/lead", json=body))

    async def lead_batch(self, urls: list[str], *, no_cache: bool = False) -> LeadBatchJob:
        """Start an async batch lead-enrichment job for 1..25 company URLs.

        Async mirror of :meth:`Webclaw.lead_batch`. Returns immediately with a
        job id; poll :meth:`get_lead_batch` or await :meth:`wait_for_lead_batch`
        until the status is ``"completed"`` or ``"failed"``. Billed 100 credits
        per *successful* lead -- error results are not charged.
        """
        body = ep.build_lead_batch_body(urls, no_cache=no_cache)
        return ep.parse_lead_batch_job(await self._request("POST", "/v1/lead/batch", json=body))

    async def get_lead_batch(self, job_id: str) -> LeadBatchStatus:
        """Get status/results of a lead batch job without polling."""
        return ep.parse_lead_batch_status(await self._request("GET", f"/v1/lead/batch/{job_id}"))

    async def wait_for_lead_batch(
        self, job_id: str, *, interval: float = 2.0, timeout: float = 600.0,
    ) -> LeadBatchStatus:
        """Poll an existing lead batch job by id until it completes or fails.

        Async mirror of :meth:`Webclaw.wait_for_lead_batch` /
        :meth:`wait_for_research` / :meth:`wait_for_crawl`.
        """
        return await _async_poll_until_done(
            fetcher=lambda: self._request("GET", f"/v1/lead/batch/{job_id}"),
            parser=ep.parse_lead_batch_status,
            label=f"Lead batch {job_id}",
            interval=interval,
            timeout=timeout,
        )

    async def summarize(self, url: str, *, max_sentences: int | None = None) -> SummarizeResponse:
        """Summarize page content."""
        return ep.parse_summarize(await self._request("POST", "/v1/summarize", json=ep.build_summarize_body(url, max_sentences=max_sentences)))

    async def brand(self, url: str) -> BrandResponse:
        """Extract brand identity from a URL."""
        return ep.parse_brand(await self._request("POST", "/v1/brand", json={"url": url}))

    async def search(self, query: str, *, num_results: int | None = None, topic: str | None = None) -> dict:
        """Run a web search query via the Serper-backed search endpoint."""
        return await self._request("POST", "/v1/search", json=ep.build_search_body(query, num_results=num_results, topic=topic))

    async def list_extractors(self) -> dict:
        """Async mirror of :meth:`Webclaw.list_extractors`.

        Returns the vertical extractor catalog as
        ``{"extractors": [{name, label, description, url_patterns}, ...]}``.
        """
        return await self._request("GET", "/v1/extractors")

    async def scrape_vertical(self, name: str, url: str) -> dict:
        """Async mirror of :meth:`Webclaw.scrape_vertical`.

        Runs a specific vertical extractor by name on the given URL.
        Returns ``{"vertical": str, "url": str, "data": dict}`` where
        ``data`` is extractor-specific typed JSON.
        """
        if not name:
            raise ValueError("name is required")
        if not url:
            raise ValueError("url is required")
        return await self._request("POST", f"/v1/scrape/{quote(name, safe='')}", json={"url": url})

    async def diff(self, url: str, **kwargs: Any) -> dict:
        """Detect content changes at a URL since the last check."""
        return await self._request("POST", "/v1/diff", json={"url": url, **kwargs})

    async def research(
        self, query: str, *, deep: bool = False,
        max_sources: int | None = None, max_iterations: int | None = None, topic: str | None = None,
    ) -> ResearchStatusResponse:
        """Start a research job and await until it completes.

        Jobs time out after 1200s (20 min) -- the server runs every
        research job in deep mode.

        :param deep: Deprecated and ignored: research always runs in deep
            mode. Passing ``deep=True`` emits a ``DeprecationWarning``.
        """
        if deep:
            warnings.warn(
                "The 'deep' parameter is deprecated and ignored: "
                "research always runs in deep mode.",
                DeprecationWarning,
                stacklevel=2,
            )
        body = ep.build_research_body(query, deep=deep, max_sources=max_sources, max_iterations=max_iterations, topic=topic)
        job_id = (await self._request("POST", "/v1/research", json=body))["id"]
        return await _async_poll_until_done(
            fetcher=lambda: self._request("GET", f"/v1/research/{job_id}"),
            parser=ep.parse_research,
            label=f"Research {job_id}",
            interval=2.0,
            timeout=1200.0,
        )

    async def get_research_status(self, job_id: str) -> ResearchStatusResponse:
        """Get status/results of a research job without polling."""
        return ep.parse_research(await self._request("GET", f"/v1/research/{job_id}"))

    async def wait_for_research(
        self, job_id: str, *, interval: float = 2.0, timeout: float = 1200.0,
    ) -> ResearchStatusResponse:
        """Poll an existing research job by id until it completes or fails.

        Async mirror of ``Webclaw.wait_for_research`` / sdk-js ``waitForResearch`` /
        sdk-go ``WaitForResearch``. Useful when the job id was persisted from
        a prior ``research()`` call and you want to block-until-done without
        restarting the job.
        """
        return await _async_poll_until_done(
            fetcher=lambda: self._request("GET", f"/v1/research/{job_id}"),
            parser=ep.parse_research,
            label=f"Research {job_id}",
            interval=interval,
            timeout=timeout,
        )

    async def wait_for_crawl(
        self, job_id: str, *, interval: float = 2.0, timeout: float = 300.0,
    ) -> CrawlStatus:
        """Poll an existing crawl job by id until it completes or fails.

        Async mirror of ``Webclaw.wait_for_crawl`` / sdk-go ``WaitForCompletion``.
        """
        return await _async_poll_until_done(
            fetcher=lambda: self.get_crawl_status(job_id),
            parser=lambda s: s,
            label=f"Crawl {job_id}",
            interval=interval,
            timeout=timeout,
            status_attr="status",
        )

    # -- watch endpoints ------------------------------------------------------

    async def watch_create(
        self, url: str, *, name: str | None = None, interval_minutes: int = 1440, webhook_url: str | None = None,
    ) -> WatchEntry:
        """Create a new watch monitor for a URL."""
        body = ep.build_watch_create_body(url, name=name, interval_minutes=interval_minutes, webhook_url=webhook_url)
        return ep.parse_watch_entry(await self._request("POST", "/v1/watch", json=body))

    async def watch_list(self, *, limit: int = 50, offset: int = 0) -> WatchListResponse:
        """List all watch monitors."""
        return ep.parse_watch_list(await self._request("GET", "/v1/watch", params={"limit": limit, "offset": offset}))

    async def watch_get(self, watch_id: str) -> WatchEntry:
        """Get a single watch monitor by ID."""
        return ep.parse_watch_entry(await self._request("GET", f"/v1/watch/{watch_id}"))

    async def watch_delete(self, watch_id: str) -> None:
        """Delete a watch monitor."""
        await self._request("DELETE", f"/v1/watch/{watch_id}")

    async def watch_check(self, watch_id: str) -> WatchCheckResponse:
        """Trigger an immediate check for a watch monitor."""
        return ep.parse_watch_check(await self._request("POST", f"/v1/watch/{watch_id}/check"))

    # -- X (Twitter) monitoring -----------------------------------------------
    #
    # Async mirror of the sync X endpoints. The X analog of watch: a monitor
    # polls X on a schedule and fires a webhook on new matches. Paid-only --
    # the server returns 403 (AuthenticationError) for free/lapsed accounts.
    # Monitors cost 1 credit per check; audience export 1 credit per page.

    async def create_x_monitor(
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

        See :meth:`Webclaw.create_x_monitor` for parameter semantics.
        """
        body = ep.build_x_monitor_create_body(
            kind, target, name=name, interval_minutes=interval_minutes,
            webhook_url=webhook_url, include_retweets=include_retweets,
            include_replies=include_replies, include_quotes=include_quotes,
            min_faves=min_faves, keyword=keyword, lang=lang,
        )
        return ep.parse_x_monitor(await self._request("POST", ep.X_MONITORS_PATH, json=body))

    async def list_x_monitors(self, *, limit: int = 50, offset: int = 0) -> XMonitorListResponse:
        """List X monitors (each a full monitor object)."""
        return ep.parse_x_monitor_list(
            await self._request("GET", ep.X_MONITORS_PATH, params={"limit": limit, "offset": offset})
        )

    async def get_x_monitor(self, monitor_id: str) -> XMonitor:
        """Get a single X monitor by id (full monitor object)."""
        return ep.parse_x_monitor(await self._request("GET", ep.x_monitor_path(monitor_id)))

    async def update_x_monitor(
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
        await self._request("PATCH", ep.x_monitor_path(monitor_id), json=body)

    async def delete_x_monitor(self, monitor_id: str) -> None:
        """Delete an X monitor."""
        await self._request("DELETE", ep.x_monitor_path(monitor_id))

    async def check_x_monitor(self, monitor_id: str) -> None:
        """Trigger an immediate background check for an X monitor (1 credit)."""
        await self._request("POST", ep.x_monitor_check_path(monitor_id))

    async def export_x_audience(
        self,
        *,
        handle: str | None = None,
        user_id: str | None = None,
        direction: str | None = None,
        cursor: str | None = None,
        max_pages: int | None = None,
    ) -> XAudienceResponse:
        """Export an account's followers or following, cursor-paginated.

        See :meth:`Webclaw.export_x_audience` for parameter semantics and the
        full-audience paging loop.
        """
        body = ep.build_x_audience_body(
            handle=handle, user_id=user_id, direction=direction,
            cursor=cursor, max_pages=max_pages,
        )
        return ep.parse_x_audience(await self._request("POST", ep.X_AUDIENCE_PATH, json=body))


class AsyncCrawlJobHandle:
    """Wraps a running crawl job with async polling helpers."""

    def __init__(self, client: AsyncWebclaw, job_id: str, status: str) -> None:
        self.client = client
        self.id = job_id
        self.status = status

    async def get_status(self) -> CrawlStatus:
        return await self.client.get_crawl_status(self.id)

    async def wait(self, *, interval: float = 2.0, timeout: float = 300.0) -> CrawlStatus:
        """Poll until the crawl completes or fails."""
        return await _async_poll_until_done(
            fetcher=self.get_status, parser=lambda s: s,
            label=f"Crawl {self.id}", interval=interval, timeout=timeout,
            status_attr="status",
        )


# -- helpers ------------------------------------------------------------------

async def _async_poll_until_done(
    *, fetcher, parser, label: str, interval: float, timeout: float, status_attr: str = "status",
) -> Any:
    """Async version of poll-until-done. See client._poll_until_done.

    Shares status classification and the terminal/unknown-state fail-fast
    logic with the sync path, and applies the same capped backoff.
    """
    deadline = time.monotonic() + timeout
    delay = interval
    transient_failures = 0
    while True:
        try:
            result = await fetcher()
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
            await asyncio.sleep(delay)
            delay = min(delay * _POLL_BACKOFF_FACTOR, _POLL_MAX_INTERVAL)
            continue
        transient_failures = 0
        status = _classify_status(result, status_attr)
        outcome = _poll_outcome(result, status, parser, label)
        if outcome is not _KEEP_POLLING:
            return outcome
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{label} did not complete within {timeout}s")
        await asyncio.sleep(delay)
        delay = min(delay * _POLL_BACKOFF_FACTOR, _POLL_MAX_INTERVAL)
