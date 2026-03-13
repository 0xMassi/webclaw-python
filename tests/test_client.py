"""Tests for the synchronous Webclaw client."""

import httpx
import pytest
import respx

from webclaw import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    Webclaw,
    WebclawError,
)

BASE = "https://api.webclaw.io"


@pytest.fixture()
def client():
    c = Webclaw("test-key", base_url=BASE)
    yield c
    c.close()


# -- scrape -------------------------------------------------------------------


@respx.mock
def test_scrape_basic(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "metadata": {"title": "Example"},
            "markdown": "# Hello",
            "text": "Hello",
            "cache": {"status": "miss"},
        })
    )
    result = client.scrape("https://example.com", formats=["markdown", "text"])
    assert result.url == "https://example.com"
    assert result.markdown == "# Hello"
    assert result.text == "Hello"
    assert result.cache is not None
    assert result.cache.status == "miss"
    assert result.metadata["title"] == "Example"
    assert result.warning is None


@respx.mock
def test_scrape_with_selectors(client: Webclaw):
    route = respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "metadata": {},
            "markdown": "filtered",
        })
    )
    client.scrape(
        "https://example.com",
        include_selectors=["article"],
        exclude_selectors=[".ads"],
        only_main_content=True,
        no_cache=True,
    )
    sent = route.calls.last.request
    body = sent.read()
    import json
    payload = json.loads(body)
    assert payload["include_selectors"] == ["article"]
    assert payload["exclude_selectors"] == [".ads"]
    assert payload["only_main_content"] is True
    assert payload["no_cache"] is True


@respx.mock
def test_scrape_with_warning(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "metadata": {},
            "warning": "Content truncated",
        })
    )
    result = client.scrape("https://example.com")
    assert result.warning == "Content truncated"


@respx.mock
def test_scrape_with_json_format(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "metadata": {},
            "json": {"key": "value"},
        })
    )
    result = client.scrape("https://example.com", formats=["json"])
    assert result.json_data == {"key": "value"}


# -- crawl --------------------------------------------------------------------


@respx.mock
def test_crawl_start(client: Webclaw):
    respx.post(f"{BASE}/v1/crawl").mock(
        return_value=httpx.Response(200, json={"id": "abc-123", "status": "running"})
    )
    handle = client.crawl("https://example.com", max_depth=3, max_pages=10)
    assert handle.id == "abc-123"
    assert handle.status == "running"


@respx.mock
def test_crawl_get_status(client: Webclaw):
    respx.get(f"{BASE}/v1/crawl/abc-123").mock(
        return_value=httpx.Response(200, json={
            "id": "abc-123",
            "status": "completed",
            "pages": [
                {"url": "https://example.com", "markdown": "# Home", "metadata": {"title": "Home"}},
                {"url": "https://example.com/about", "markdown": "# About", "metadata": {}},
            ],
            "total": 2,
            "completed": 2,
            "errors": 0,
        })
    )
    status = client.get_crawl_status("abc-123")
    assert status.status == "completed"
    assert len(status.pages) == 2
    assert status.pages[0].url == "https://example.com"
    assert status.pages[0].markdown == "# Home"
    assert status.total == 2
    assert status.errors == 0


@respx.mock
def test_crawl_wait(client: Webclaw):
    """wait() should poll until status is 'completed'."""
    respx.post(f"{BASE}/v1/crawl").mock(
        return_value=httpx.Response(200, json={"id": "job-1", "status": "running"})
    )

    call_count = 0

    def respond(request):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(200, json={
                "id": "job-1", "status": "running",
                "pages": [], "total": 5, "completed": call_count, "errors": 0,
            })
        return httpx.Response(200, json={
            "id": "job-1", "status": "completed",
            "pages": [{"url": "https://example.com", "markdown": "done", "metadata": {}}],
            "total": 1, "completed": 1, "errors": 0,
        })

    respx.get(f"{BASE}/v1/crawl/job-1").mock(side_effect=respond)

    handle = client.crawl("https://example.com")
    result = handle.wait(interval=0.01, timeout=5.0)
    assert result.status == "completed"
    assert call_count == 3


@respx.mock
def test_crawl_wait_timeout(client: Webclaw):
    respx.post(f"{BASE}/v1/crawl").mock(
        return_value=httpx.Response(200, json={"id": "slow", "status": "running"})
    )
    respx.get(f"{BASE}/v1/crawl/slow").mock(
        return_value=httpx.Response(200, json={
            "id": "slow", "status": "running",
            "pages": [], "total": 100, "completed": 0, "errors": 0,
        })
    )
    handle = client.crawl("https://example.com")
    with pytest.raises(Exception, match="did not complete"):
        handle.wait(interval=0.01, timeout=0.05)


@respx.mock
def test_crawl_page_with_error(client: Webclaw):
    respx.get(f"{BASE}/v1/crawl/err-1").mock(
        return_value=httpx.Response(200, json={
            "id": "err-1",
            "status": "completed",
            "pages": [
                {"url": "https://example.com/broken", "error": "HTTP 500", "metadata": {}},
            ],
            "total": 1, "completed": 0, "errors": 1,
        })
    )
    status = client.get_crawl_status("err-1")
    assert status.errors == 1
    assert status.pages[0].error == "HTTP 500"


# -- map ----------------------------------------------------------------------


@respx.mock
def test_map(client: Webclaw):
    respx.post(f"{BASE}/v1/map").mock(
        return_value=httpx.Response(200, json={
            "urls": ["https://example.com", "https://example.com/about"],
            "count": 2,
        })
    )
    result = client.map("https://example.com")
    assert result.count == 2
    assert len(result.urls) == 2


# -- batch --------------------------------------------------------------------


@respx.mock
def test_batch(client: Webclaw):
    respx.post(f"{BASE}/v1/batch").mock(
        return_value=httpx.Response(200, json={
            "results": [
                {"url": "https://a.com", "markdown": "# A", "metadata": {"title": "A"}},
                {"url": "https://b.com", "error": "timeout"},
            ]
        })
    )
    result = client.batch(["https://a.com", "https://b.com"], formats=["markdown"])
    assert len(result.results) == 2
    assert result.results[0].markdown == "# A"
    assert result.results[1].error == "timeout"


@respx.mock
def test_batch_sends_concurrency(client: Webclaw):
    route = respx.post(f"{BASE}/v1/batch").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client.batch(["https://a.com"], concurrency=10)
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["concurrency"] == 10


# -- extract ------------------------------------------------------------------


@respx.mock
def test_extract(client: Webclaw):
    respx.post(f"{BASE}/v1/extract").mock(
        return_value=httpx.Response(200, json={
            "data": {"name": "Webclaw", "pricing": "$49/mo"},
        })
    )
    result = client.extract(
        "https://example.com",
        schema={"type": "object", "properties": {"name": {"type": "string"}}},
        prompt="Extract company info",
    )
    assert result.data["name"] == "Webclaw"


@respx.mock
def test_extract_without_schema(client: Webclaw):
    route = respx.post(f"{BASE}/v1/extract").mock(
        return_value=httpx.Response(200, json={"data": {"key": "val"}})
    )
    client.extract("https://example.com")
    import json
    payload = json.loads(route.calls.last.request.read())
    assert "schema" not in payload
    assert "prompt" not in payload


# -- summarize ----------------------------------------------------------------


@respx.mock
def test_summarize(client: Webclaw):
    respx.post(f"{BASE}/v1/summarize").mock(
        return_value=httpx.Response(200, json={"summary": "Example is a test site."})
    )
    result = client.summarize("https://example.com", max_sentences=3)
    assert result.summary == "Example is a test site."


@respx.mock
def test_summarize_no_max_sentences(client: Webclaw):
    route = respx.post(f"{BASE}/v1/summarize").mock(
        return_value=httpx.Response(200, json={"summary": "short"})
    )
    client.summarize("https://example.com")
    import json
    payload = json.loads(route.calls.last.request.read())
    assert "max_sentences" not in payload


# -- brand --------------------------------------------------------------------


@respx.mock
def test_brand(client: Webclaw):
    respx.post(f"{BASE}/v1/brand").mock(
        return_value=httpx.Response(200, json={
            "name": "Example Corp",
            "colors": ["#fff", "#000"],
            "logo": "https://example.com/logo.png",
        })
    )
    result = client.brand("https://example.com")
    assert result.data["name"] == "Example Corp"
    assert result.data["colors"] == ["#fff", "#000"]


# -- error handling -----------------------------------------------------------


@respx.mock
def test_auth_error(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(401, json={"error": "Unauthorized"})
    )
    with pytest.raises(AuthenticationError, match="Unauthorized"):
        client.scrape("https://example.com")


@respx.mock
def test_auth_error_403(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(403, json={"error": "Forbidden"})
    )
    with pytest.raises(AuthenticationError):
        client.scrape("https://example.com")


@respx.mock
def test_not_found_error(client: Webclaw):
    respx.get(f"{BASE}/v1/crawl/missing").mock(
        return_value=httpx.Response(404, json={"error": "Job not found"})
    )
    with pytest.raises(NotFoundError, match="Job not found"):
        client.get_crawl_status("missing")


@respx.mock
def test_rate_limit_error(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(429, json={"error": "Too many requests"})
    )
    with pytest.raises(RateLimitError, match="Too many requests"):
        client.scrape("https://example.com")


@respx.mock
def test_generic_server_error(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(500, json={"error": "Internal server error"})
    )
    with pytest.raises(WebclawError) as exc_info:
        client.scrape("https://example.com")
    assert exc_info.value.status_code == 500


@respx.mock
def test_error_without_json_body(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(502, text="Bad Gateway")
    )
    with pytest.raises(WebclawError, match="Bad Gateway"):
        client.scrape("https://example.com")


# -- client config ------------------------------------------------------------


def test_auth_header():
    c = Webclaw("my-secret-key")
    assert c._client.headers["authorization"] == "Bearer my-secret-key"
    c.close()


def test_custom_base_url():
    c = Webclaw("key", base_url="https://custom.api.com/")
    assert c.base_url == "https://custom.api.com"
    c.close()


def test_context_manager():
    with Webclaw("key") as c:
        assert c.api_key == "key"
    # client should be closed after exiting context -- no way to assert directly
    # but at least verify no exception is raised
