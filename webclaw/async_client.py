"""Asynchronous Webclaw client."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Sequence

import httpx

from .client import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    _parse_batch,
    _parse_crawl_status,
    _parse_research,
    _parse_scrape,
    _raise_for_status,
)
from .errors import TimeoutError, WebclawError
from .types import (
    BatchResponse,
    BrandResponse,
    CrawlJob,
    CrawlStatus,
    ExtractResponse,
    MapResponse,
    ResearchStartResponse,
    ResearchStatusResponse,
    ScrapeResponse,
    SummarizeResponse,
    WatchCheckResponse,
    WatchEntry,
    WatchListResponse,
)


class AsyncWebclaw:
    """Async client for the Webclaw web extraction API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    # -- lifecycle ------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncWebclaw":
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
        formats: Optional[Sequence[str]] = None,
        include_selectors: Optional[List[str]] = None,
        exclude_selectors: Optional[List[str]] = None,
        only_main_content: bool = False,
        no_cache: bool = False,
    ) -> ScrapeResponse:
        body: Dict[str, Any] = {"url": url}
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

        data = await self._request("POST", "/v1/scrape", json=body)
        return _parse_scrape(data)

    async def crawl(
        self,
        url: str,
        *,
        max_depth: int = 2,
        max_pages: int = 50,
        use_sitemap: bool = False,
    ) -> AsyncCrawlJobHandle:
        body: Dict[str, Any] = {
            "url": url,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "use_sitemap": use_sitemap,
        }
        data = await self._request("POST", "/v1/crawl", json=body)
        job = CrawlJob(id=data["id"], status=data["status"])
        return AsyncCrawlJobHandle(client=self, job=job)

    async def get_crawl_status(self, job_id: str) -> CrawlStatus:
        data = await self._request("GET", f"/v1/crawl/{job_id}")
        return _parse_crawl_status(data)

    async def map(self, url: str) -> MapResponse:
        data = await self._request("POST", "/v1/map", json={"url": url})
        return MapResponse(urls=data.get("urls", []), count=data.get("count", 0))

    async def batch(
        self,
        urls: List[str],
        *,
        formats: Optional[Sequence[str]] = None,
        concurrency: int = 5,
    ) -> BatchResponse:
        body: Dict[str, Any] = {"urls": urls, "concurrency": concurrency}
        if formats is not None:
            body["formats"] = list(formats)
        data = await self._request("POST", "/v1/batch", json=body)
        return _parse_batch(data)

    async def extract(
        self,
        url: str,
        *,
        schema: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
    ) -> ExtractResponse:
        body: Dict[str, Any] = {"url": url}
        if schema is not None:
            body["schema"] = schema
        if prompt is not None:
            body["prompt"] = prompt
        data = await self._request("POST", "/v1/extract", json=body)
        return ExtractResponse(data=data.get("data"))

    async def summarize(
        self,
        url: str,
        *,
        max_sentences: Optional[int] = None,
    ) -> SummarizeResponse:
        body: Dict[str, Any] = {"url": url}
        if max_sentences is not None:
            body["max_sentences"] = max_sentences
        data = await self._request("POST", "/v1/summarize", json=body)
        return SummarizeResponse(summary=data.get("summary", ""))

    async def brand(self, url: str) -> BrandResponse:
        data = await self._request("POST", "/v1/brand", json={"url": url})
        return BrandResponse(data=data)

    async def search(
        self,
        query: str,
        *,
        num_results: Optional[int] = None,
        topic: Optional[str] = None,
    ) -> dict:
        """Run a web search query via the Serper-backed search endpoint."""
        body: Dict[str, Any] = {"query": query}
        if num_results is not None:
            body["num_results"] = num_results
        if topic is not None:
            body["topic"] = topic
        return await self._request("POST", "/v1/search", json=body)

    async def diff(self, url: str, **kwargs: Any) -> dict:
        """Detect content changes at a URL since the last check."""
        return await self._request("POST", "/v1/diff", json={"url": url, **kwargs})

    async def agent_scrape(self, url: str, goal: str, **kwargs: Any) -> dict:
        """AI-guided scraping that navigates a page to achieve a goal."""
        return await self._request("POST", "/v1/agent-scrape", json={"url": url, "goal": goal, **kwargs})

    async def research(
        self,
        query: str,
        *,
        deep: bool = False,
        max_sources: Optional[int] = None,
        max_iterations: Optional[int] = None,
        topic: Optional[str] = None,
    ) -> ResearchStatusResponse:
        """Start a research job and poll until it completes.

        Awaits until the server finishes research. Normal queries time out
        after 600s, deep research after 1200s.
        """
        body: Dict[str, Any] = {"query": query, "deep": deep}
        if max_sources is not None:
            body["max_sources"] = max_sources
        if max_iterations is not None:
            body["max_iterations"] = max_iterations
        if topic is not None:
            body["topic"] = topic

        data = await self._request("POST", "/v1/research", json=body)
        job_id = data["id"]
        poll_timeout = 1200.0 if deep else 600.0
        deadline = time.monotonic() + poll_timeout

        while True:
            result = await self._request("GET", f"/v1/research/{job_id}")
            status = result.get("status", "")
            if status == "completed":
                return _parse_research(result)
            if status == "failed":
                raise WebclawError(
                    result.get("error", "Research job failed"),
                    status_code=None,
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Research {job_id} did not complete within {poll_timeout}s"
                )
            await asyncio.sleep(2.0)

    async def get_research_status(self, job_id: str) -> ResearchStatusResponse:
        """Get status/results of a research job."""
        data = await self._request("GET", f"/v1/research/{job_id}")
        return _parse_research(data)

    # -- watch endpoints ------------------------------------------------------

    async def watch_create(
        self,
        url: str,
        *,
        name: Optional[str] = None,
        interval_minutes: int = 1440,
        webhook_url: Optional[str] = None,
    ) -> WatchEntry:
        """Create a new watch monitor for a URL."""
        body: Dict[str, Any] = {"url": url, "interval_minutes": interval_minutes}
        if name is not None:
            body["name"] = name
        if webhook_url is not None:
            body["webhook_url"] = webhook_url
        data = await self._request("POST", "/v1/watch", json=body)
        return WatchEntry.from_dict(data)

    async def watch_list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> WatchListResponse:
        """List all watch monitors."""
        data = await self._request("GET", "/v1/watch", params={"limit": limit, "offset": offset})
        watches = [WatchEntry.from_dict(w) for w in data.get("watches", [])]
        return WatchListResponse(watches=watches, total=data.get("total", len(watches)))

    async def watch_get(self, watch_id: str) -> WatchEntry:
        """Get a single watch monitor by ID."""
        data = await self._request("GET", f"/v1/watch/{watch_id}")
        return WatchEntry.from_dict(data)

    async def watch_delete(self, watch_id: str) -> None:
        """Delete a watch monitor."""
        await self._request("DELETE", f"/v1/watch/{watch_id}")

    async def watch_check(self, watch_id: str) -> WatchCheckResponse:
        """Trigger an immediate check for a watch monitor."""
        data = await self._request("POST", f"/v1/watch/{watch_id}/check")
        return WatchCheckResponse(
            id=data.get("id", ""),
            has_changed=data.get("has_changed", False),
            diff=data.get("diff"),
            checked_at=data.get("checked_at", ""),
        )


class AsyncCrawlJobHandle:
    """Wraps a running crawl job with async polling helpers."""

    def __init__(self, client: AsyncWebclaw, job: CrawlJob) -> None:
        self.client = client
        self.id = job.id
        self.status = job.status

    async def get_status(self) -> CrawlStatus:
        return await self.client.get_crawl_status(self.id)

    async def wait(
        self,
        *,
        interval: float = 2.0,
        timeout: float = 300.0,
    ) -> CrawlStatus:
        """Poll until the crawl completes or fails, then return final status."""
        deadline = time.monotonic() + timeout
        while True:
            result = await self.get_status()
            if result.status in ("completed", "failed"):
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Crawl {self.id} did not complete within {timeout}s"
                )
            await asyncio.sleep(interval)
