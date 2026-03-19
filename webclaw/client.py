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
    WatchCheckResponse,
    WatchEntry,
    WatchListResponse,
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

    def search(
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
        return self._request("POST", "/v1/search", json=body)

    def diff(self, url: str, **kwargs: Any) -> dict:
        """Detect content changes at a URL since the last check."""
        return self._request("POST", "/v1/diff", json={"url": url, **kwargs})

    def agent_scrape(self, url: str, goal: str, **kwargs: Any) -> dict:
        """AI-guided scraping that navigates a page to achieve a goal."""
        return self._request("POST", "/v1/agent-scrape", json={"url": url, "goal": goal, **kwargs})

    def research(
        self,
        query: str,
        *,
        deep: bool = False,
        max_sources: Optional[int] = None,
        max_iterations: Optional[int] = None,
        topic: Optional[str] = None,
    ) -> ResearchStatusResponse:
        """Start a research job and poll until it completes.

        Blocks until the server finishes research. Normal queries time out
        after 600s, deep research after 1200s.
        """
        body: Dict[str, Any] = {"query": query, "deep": deep}
        if max_sources is not None:
            body["max_sources"] = max_sources
        if max_iterations is not None:
            body["max_iterations"] = max_iterations
        if topic is not None:
            body["topic"] = topic

        data = self._request("POST", "/v1/research", json=body)
        job_id = data["id"]
        poll_timeout = 1200.0 if deep else 600.0
        deadline = time.monotonic() + poll_timeout

        while True:
            result = self._request("GET", f"/v1/research/{job_id}")
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
            time.sleep(2.0)

    def get_research_status(self, job_id: str) -> ResearchStatusResponse:
        """Get status/results of a research job."""
        data = self._request("GET", f"/v1/research/{job_id}")
        return _parse_research(data)

    # -- watch endpoints ------------------------------------------------------

    def watch_create(
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
        data = self._request("POST", "/v1/watch", json=body)
        return WatchEntry.from_dict(data)

    def watch_list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> WatchListResponse:
        """List all watch monitors."""
        data = self._request("GET", "/v1/watch", params={"limit": limit, "offset": offset})
        watches = [WatchEntry.from_dict(w) for w in data.get("watches", [])]
        return WatchListResponse(watches=watches, total=data.get("total", len(watches)))

    def watch_get(self, watch_id: str) -> WatchEntry:
        """Get a single watch monitor by ID."""
        data = self._request("GET", f"/v1/watch/{watch_id}")
        return WatchEntry.from_dict(data)

    def watch_delete(self, watch_id: str) -> None:
        """Delete a watch monitor."""
        self._request("DELETE", f"/v1/watch/{watch_id}")

    def watch_check(self, watch_id: str) -> WatchCheckResponse:
        """Trigger an immediate check for a watch monitor."""
        data = self._request("POST", f"/v1/watch/{watch_id}/check")
        return WatchCheckResponse(
            id=data.get("id", ""),
            has_changed=data.get("has_changed", False),
            diff=data.get("diff"),
            checked_at=data.get("checked_at", ""),
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


def _parse_research(data: Dict[str, Any]) -> ResearchStatusResponse:
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
