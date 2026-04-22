"""Synchronous Webclaw client."""

from __future__ import annotations

import time
from typing import Any, Sequence

import httpx

from . import _endpoints as ep
from .errors import AuthenticationError, NotFoundError, RateLimitError, TimeoutError, WebclawError
from .types import (
    BatchResponse, BrandResponse, CrawlStatus, ExtractResponse, MapResponse,
    ResearchStatusResponse, ScrapeResponse, SummarizeResponse,
    WatchCheckResponse, WatchEntry, WatchListResponse,
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
        response = self._client.request(method, path, **kwargs)
        _raise_for_status(response)
        return response.json()

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
        from urllib.parse import quote
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

def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    try:
        detail = response.json().get("error", response.text)
    except (ValueError, KeyError):
        detail = response.text

    if response.status_code in (401, 403):
        raise AuthenticationError(str(detail))
    if response.status_code == 404:
        raise NotFoundError(str(detail))
    if response.status_code == 429:
        raise RateLimitError(str(detail))
    raise WebclawError(str(detail), status_code=response.status_code)


def _poll_until_done(
    *, fetcher, parser, label: str, interval: float, timeout: float, status_attr: str = "status",
) -> Any:
    """Poll fetcher() until terminal state, then return parser(result).

    For research: fetcher returns raw dict, parser converts to dataclass.
    For crawl: fetcher returns CrawlStatus, parser is identity.
    """
    deadline = time.monotonic() + timeout
    while True:
        result = fetcher()
        status = result.get("status", "") if isinstance(result, dict) else getattr(result, status_attr)
        if status == "completed":
            return parser(result)
        if status == "failed":
            error = result.get("error", f"{label} failed") if isinstance(result, dict) else f"{label} failed"
            raise WebclawError(error, status_code=None)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{label} did not complete within {timeout}s")
        time.sleep(interval)
