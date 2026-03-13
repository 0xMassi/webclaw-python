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
    _parse_scrape,
    _raise_for_status,
)
from .errors import TimeoutError
from .types import (
    BatchResponse,
    BrandResponse,
    CrawlJob,
    CrawlStatus,
    ExtractResponse,
    MapResponse,
    ScrapeResponse,
    SummarizeResponse,
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
