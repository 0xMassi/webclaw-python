"""Tests for the asynchronous Webclaw client."""

import httpx
import pytest
import respx

from webclaw import (
    AsyncWebclaw,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    WebclawError,
)

BASE = "https://api.webclaw.io"


@pytest.fixture()
async def client():
    c = AsyncWebclaw("test-key", base_url=BASE)
    yield c
    await c.close()


# -- scrape -------------------------------------------------------------------


@respx.mock
async def test_scrape_basic(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "metadata": {"title": "Example"},
            "markdown": "# Hello",
            "text": "Hello",
            "llm": "clean text for llm",
            "cache": {"status": "hit"},
        })
    )
    result = await client.scrape("https://example.com", formats=["markdown", "text", "llm"])
    assert result.url == "https://example.com"
    assert result.markdown == "# Hello"
    assert result.llm == "clean text for llm"
    assert result.cache is not None
    assert result.cache.status == "hit"


@respx.mock
async def test_scrape_with_options(client: AsyncWebclaw):
    route = respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "metadata": {},
        })
    )
    await client.scrape(
        "https://example.com",
        include_selectors=["main"],
        exclude_selectors=[".nav"],
        only_main_content=True,
        no_cache=True,
    )
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["only_main_content"] is True
    assert payload["no_cache"] is True
    assert payload["include_selectors"] == ["main"]


# -- crawl --------------------------------------------------------------------


@respx.mock
async def test_crawl_start(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/crawl").mock(
        return_value=httpx.Response(200, json={"id": "async-1", "status": "running"})
    )
    handle = await client.crawl("https://example.com", max_depth=1, use_sitemap=True)
    assert handle.id == "async-1"


@respx.mock
async def test_crawl_get_status(client: AsyncWebclaw):
    respx.get(f"{BASE}/v1/crawl/async-1").mock(
        return_value=httpx.Response(200, json={
            "id": "async-1",
            "status": "completed",
            "pages": [{"url": "https://example.com", "markdown": "# Done", "metadata": {}}],
            "total": 1, "completed": 1, "errors": 0,
        })
    )
    status = await client.get_crawl_status("async-1")
    assert status.status == "completed"
    assert status.pages[0].markdown == "# Done"


@respx.mock
async def test_crawl_wait(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/crawl").mock(
        return_value=httpx.Response(200, json={"id": "w-1", "status": "running"})
    )

    call_count = 0

    def respond(request):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(200, json={
                "id": "w-1", "status": "running",
                "pages": [], "total": 3, "completed": 0, "errors": 0,
            })
        return httpx.Response(200, json={
            "id": "w-1", "status": "completed",
            "pages": [{"url": "https://example.com", "markdown": "ok", "metadata": {}}],
            "total": 1, "completed": 1, "errors": 0,
        })

    respx.get(f"{BASE}/v1/crawl/w-1").mock(side_effect=respond)

    handle = await client.crawl("https://example.com")
    result = await handle.wait(interval=0.01, timeout=5.0)
    assert result.status == "completed"
    assert call_count == 2


@respx.mock
async def test_crawl_wait_timeout(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/crawl").mock(
        return_value=httpx.Response(200, json={"id": "slow-async", "status": "running"})
    )
    respx.get(f"{BASE}/v1/crawl/slow-async").mock(
        return_value=httpx.Response(200, json={
            "id": "slow-async", "status": "running",
            "pages": [], "total": 99, "completed": 0, "errors": 0,
        })
    )
    handle = await client.crawl("https://example.com")
    with pytest.raises(Exception, match="did not complete"):
        await handle.wait(interval=0.01, timeout=0.05)


# -- map ----------------------------------------------------------------------


@respx.mock
async def test_map(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/map").mock(
        return_value=httpx.Response(200, json={
            "urls": ["https://example.com/a", "https://example.com/b"],
            "count": 2,
        })
    )
    result = await client.map("https://example.com")
    assert result.count == 2
    assert "https://example.com/a" in result.urls


# -- batch --------------------------------------------------------------------


@respx.mock
async def test_batch(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/batch").mock(
        return_value=httpx.Response(200, json={
            "results": [
                {"url": "https://a.com", "markdown": "# A", "metadata": {}},
                {"url": "https://b.com", "error": "failed"},
            ]
        })
    )
    result = await client.batch(["https://a.com", "https://b.com"])
    assert len(result.results) == 2
    assert result.results[0].markdown == "# A"
    assert result.results[1].error == "failed"


# -- extract ------------------------------------------------------------------


@respx.mock
async def test_extract(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/extract").mock(
        return_value=httpx.Response(200, json={"data": {"price": "$10"}})
    )
    result = await client.extract("https://example.com", prompt="Get price")
    assert result.data["price"] == "$10"


# -- summarize ----------------------------------------------------------------


@respx.mock
async def test_summarize(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/summarize").mock(
        return_value=httpx.Response(200, json={"summary": "A short summary."})
    )
    result = await client.summarize("https://example.com", max_sentences=2)
    assert result.summary == "A short summary."


# -- brand --------------------------------------------------------------------


@respx.mock
async def test_brand(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/brand").mock(
        return_value=httpx.Response(200, json={
            "name": "Acme",
            "logo": "https://acme.com/logo.svg",
        })
    )
    result = await client.brand("https://acme.com")
    assert result.data["name"] == "Acme"


# -- error handling -----------------------------------------------------------


@respx.mock
async def test_auth_error(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(401, json={"error": "Unauthorized"})
    )
    with pytest.raises(AuthenticationError):
        await client.scrape("https://example.com")


@respx.mock
async def test_not_found_error(client: AsyncWebclaw):
    respx.get(f"{BASE}/v1/crawl/nope").mock(
        return_value=httpx.Response(404, json={"error": "Not found"})
    )
    with pytest.raises(NotFoundError):
        await client.get_crawl_status("nope")


@respx.mock
async def test_rate_limit_error(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(429, json={"error": "Slow down"})
    )
    with pytest.raises(RateLimitError):
        await client.scrape("https://example.com")


@respx.mock
async def test_server_error(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(500, json={"error": "Boom"})
    )
    with pytest.raises(WebclawError) as exc_info:
        await client.scrape("https://example.com")
    assert exc_info.value.status_code == 500


# -- client config ------------------------------------------------------------


async def test_auth_header():
    c = AsyncWebclaw("secret-123")
    assert c._client.headers["authorization"] == "Bearer secret-123"
    await c.close()


async def test_context_manager():
    async with AsyncWebclaw("key") as c:
        assert c.api_key == "key"
