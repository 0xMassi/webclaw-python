"""Synchronous Webclaw client."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

import httpx

from .errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
    WebclawError,
)
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
    ResearchStartResponse,
    ResearchStatusResponse,
    ScrapeResponse,
    SummarizeResponse,
)

DEFAULT_BASE_URL = "https://api.webclaw.io"
DEFAULT_TIMEOUT = 30.0


class Webclaw:
    """Synchronous client for the Webclaw web extraction API."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Webclaw":
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

        data = self._request("POST", "/v1/scrape", json=body)
        return _parse_scrape(data)

    def crawl(
        self,
        url: str,
        *,
        max_depth: int = 2,
        max_pages: int = 50,
        use_sitemap: bool = False,
    ) -> CrawlJobHandle:
        body: Dict[str, Any] = {
            "url": url,
            "max_depth": max_depth,
            "max_pages": max_pages,
            "use_sitemap": use_sitemap,
        }
        data = self._request("POST", "/v1/crawl", json=body)
        job = CrawlJob(id=data["id"], status=data["status"])
        return CrawlJobHandle(client=self, job=job)

    def get_crawl_status(self, job_id: str) -> CrawlStatus:
        data = self._request("GET", f"/v1/crawl/{job_id}")
        return _parse_crawl_status(data)

    def map(self, url: str) -> MapResponse:
        data = self._request("POST", "/v1/map", json={"url": url})
        return MapResponse(urls=data.get("urls", []), count=data.get("count", 0))

    def batch(
        self,
        urls: List[str],
        *,
        formats: Optional[Sequence[str]] = None,
        concurrency: int = 5,
    ) -> BatchResponse:
        body: Dict[str, Any] = {"urls": urls, "concurrency": concurrency}
        if formats is not None:
            body["formats"] = list(formats)
        data = self._request("POST", "/v1/batch", json=body)
        return _parse_batch(data)

    def extract(
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
        data = self._request("POST", "/v1/extract", json=body)
        return ExtractResponse(data=data.get("data"))

    def summarize(
        self,
        url: str,
        *,
        max_sentences: Optional[int] = None,
    ) -> SummarizeResponse:
        body: Dict[str, Any] = {"url": url}
        if max_sentences is not None:
            body["max_sentences"] = max_sentences
        data = self._request("POST", "/v1/summarize", json=body)
        return SummarizeResponse(summary=data.get("summary", ""))

    def brand(self, url: str) -> BrandResponse:
        data = self._request("POST", "/v1/brand", json={"url": url})
        return BrandResponse(data=data)

    def search(self, query: str, **kwargs: Any) -> dict:
        """Run a web search query via the Serper-backed search endpoint."""
        return self._request("POST", "/v1/search", json={"query": query, **kwargs})

    def diff(self, url: str, **kwargs: Any) -> dict:
        """Detect content changes at a URL since the last check."""
        return self._request("POST", "/v1/diff", json={"url": url, **kwargs})

    def agent_scrape(self, url: str, goal: str, **kwargs: Any) -> dict:
        """AI-guided scraping that navigates a page to achieve a goal."""
        return self._request("POST", "/v1/agent-scrape", json={"url": url, "goal": goal, **kwargs})

    def research(self, query: str, **kwargs: Any) -> ResearchStartResponse:
        """Start an async research job. Returns job ID for polling."""
        data = self._request("POST", "/v1/research", json={"query": query, **kwargs})
        return ResearchStartResponse(id=data.get("id", ""), status=data.get("status", ""))

    def get_research_status(self, job_id: str) -> ResearchStatusResponse:
        """Get status/results of a research job."""
        data = self._request("GET", f"/v1/research/{job_id}")
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


class CrawlJobHandle:
    """Wraps a running crawl job with polling helpers."""

    def __init__(self, client: Webclaw, job: CrawlJob) -> None:
        self.client = client
        self.id = job.id
        self.status = job.status

    def get_status(self) -> CrawlStatus:
        return self.client.get_crawl_status(self.id)

    def wait(
        self,
        *,
        interval: float = 2.0,
        timeout: float = 300.0,
    ) -> CrawlStatus:
        """Poll until the crawl completes or fails, then return final status."""
        deadline = time.monotonic() + timeout
        while True:
            result = self.get_status()
            if result.status in ("completed", "failed"):
                return result
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Crawl {self.id} did not complete within {timeout}s"
                )
            time.sleep(interval)


# -- shared helpers -----------------------------------------------------------

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


def _parse_scrape(data: Dict[str, Any]) -> ScrapeResponse:
    cache = None
    if "cache" in data and data["cache"]:
        cache = CacheInfo(status=data["cache"]["status"])
    return ScrapeResponse(
        url=data["url"],
        metadata=data.get("metadata", {}),
        markdown=data.get("markdown"),
        text=data.get("text"),
        llm=data.get("llm"),
        json_data=data.get("json"),
        cache=cache,
        warning=data.get("warning"),
    )


def _parse_crawl_status(data: Dict[str, Any]) -> CrawlStatus:
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


def _parse_batch(data: Dict[str, Any]) -> BatchResponse:
    results = [
        BatchResult(
            url=r["url"],
            markdown=r.get("markdown"),
            metadata=r.get("metadata", {}),
            error=r.get("error"),
        )
        for r in data.get("results", [])
    ]
    return BatchResponse(results=results)
