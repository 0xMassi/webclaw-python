"""Asynchronous Webclaw client."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Sequence

import httpx

from . import _endpoints as ep
from .client import _raise_for_status
from .errors import TimeoutError, WebclawError
from .types import (
    BatchResponse, BrandResponse, CrawlStatus, ExtractResponse, MapResponse,
    ResearchStatusResponse, ScrapeResponse, SummarizeResponse,
    WatchCheckResponse, WatchEntry, WatchListResponse,
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
        response = await self._client.request(method, path, **kwargs)
        _raise_for_status(response)
        return response.json()

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

    async def summarize(self, url: str, *, max_sentences: int | None = None) -> SummarizeResponse:
        """Summarize page content."""
        return ep.parse_summarize(await self._request("POST", "/v1/summarize", json=ep.build_summarize_body(url, max_sentences=max_sentences)))

    async def brand(self, url: str) -> BrandResponse:
        """Extract brand identity from a URL."""
        return ep.parse_brand(await self._request("POST", "/v1/brand", json={"url": url}))

    async def search(self, query: str, *, num_results: int | None = None, topic: str | None = None) -> dict:
        """Run a web search query via the Serper-backed search endpoint."""
        return await self._request("POST", "/v1/search", json=ep.build_search_body(query, num_results=num_results, topic=topic))

    async def diff(self, url: str, **kwargs: Any) -> dict:
        """Detect content changes at a URL since the last check."""
        return await self._request("POST", "/v1/diff", json={"url": url, **kwargs})

    async def research(
        self, query: str, *, deep: bool = False,
        max_sources: int | None = None, max_iterations: int | None = None, topic: str | None = None,
    ) -> ResearchStatusResponse:
        """Start a research job and await until it completes.

        Normal queries time out after 600s, deep research after 1200s.
        """
        body = ep.build_research_body(query, deep=deep, max_sources=max_sources, max_iterations=max_iterations, topic=topic)
        job_id = (await self._request("POST", "/v1/research", json=body))["id"]
        return await _async_poll_until_done(
            fetcher=lambda: self._request("GET", f"/v1/research/{job_id}"),
            parser=ep.parse_research,
            label=f"Research {job_id}",
            interval=2.0,
            timeout=1200.0 if deep else 600.0,
        )

    async def get_research_status(self, job_id: str) -> ResearchStatusResponse:
        """Get status/results of a research job without polling."""
        return ep.parse_research(await self._request("GET", f"/v1/research/{job_id}"))

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
    """Async version of poll-until-done. See client._poll_until_done."""
    deadline = time.monotonic() + timeout
    while True:
        result = await fetcher()
        status = result.get("status", "") if isinstance(result, dict) else getattr(result, status_attr)
        if status == "completed":
            return parser(result)
        if status == "failed":
            error = result.get("error", f"{label} failed") if isinstance(result, dict) else f"{label} failed"
            raise WebclawError(error, status_code=None)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{label} did not complete within {timeout}s")
        await asyncio.sleep(interval)
