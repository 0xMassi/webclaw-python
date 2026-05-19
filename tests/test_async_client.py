"""Tests for the asynchronous Webclaw client."""

import httpx
import pytest
import respx

from webclaw import (
    AsyncWebclaw,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
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


# -- endpoints ----------------------------------------------------------------


@respx.mock
async def test_endpoints_success_shape(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/endpoints").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "bundles_scanned": 2,
            "endpoint_count": 1,
            "endpoints": [
                {"value": "https://api.example.com/graphql", "kind": "graph_ql",
                 "first_party": False, "source": "vendor.js"},
            ],
            "hosts": ["api.example.com"],
            "truncated": True,
        })
    )
    res = await client.endpoints("https://example.com", include_third_party=True)
    assert res.url == "https://example.com"
    assert res.bundles_scanned == 2
    assert res.truncated is True
    assert len(res.endpoints) == 1
    ep = res.endpoints[0]
    assert ep.value == "https://api.example.com/graphql"
    assert ep.kind == "graph_ql"
    assert ep.first_party is False
    assert ep.source == "vendor.js"


@respx.mock
async def test_endpoints_params_passthrough(client: AsyncWebclaw):
    route = respx.post(f"{BASE}/v1/endpoints").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com", "bundles_scanned": 0,
            "endpoint_count": 0, "endpoints": [], "hosts": [], "truncated": False,
        })
    )
    await client.endpoints(
        "https://example.com", include_third_party=True, max_bundles=15,
    )
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["include_third_party"] is True
    assert payload["max_bundles"] == 15


@respx.mock
async def test_endpoints_400(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/endpoints").mock(
        return_value=httpx.Response(400, json={"error": "invalid url"})
    )
    with pytest.raises(WebclawError, match="invalid url") as exc:
        await client.endpoints("bad")
    assert exc.value.status_code == 400


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


# -- Fix 1: error robustness + httpx mapping (async) --------------------------


@respx.mock
async def test_error_body_json_array_does_not_crash(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(500, json=["boom"])
    )
    with pytest.raises(WebclawError) as exc:
        await client.scrape("https://example.com")
    assert exc.value.status_code == 500


@respx.mock
async def test_timeout_exception_mapped(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        side_effect=httpx.ReadTimeout("slow")
    )
    with pytest.raises(TimeoutError):
        await client.scrape("https://example.com")


@respx.mock
async def test_transport_error_mapped(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with pytest.raises(WebclawError) as exc:
        await client.scrape("https://example.com")
    assert not isinstance(exc.value, httpx.HTTPError)


# -- Fix 2: poll fail-fast + backoff (async) ----------------------------------


@respx.mock
async def test_research_failed_fails_fast(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/research").mock(
        return_value=httpx.Response(200, json={"id": "ar"})
    )
    respx.get(f"{BASE}/v1/research/ar").mock(
        return_value=httpx.Response(200, json={"id": "ar", "status": "failed", "error": "nope"})
    )
    with pytest.raises(WebclawError, match="nope"):
        await client.research("q")


@respx.mock
async def test_unknown_status_fails_fast(client: AsyncWebclaw):
    respx.get(f"{BASE}/v1/crawl/aw").mock(
        return_value=httpx.Response(200, json={
            "id": "aw", "status": "levitating",
            "pages": [], "total": 0, "completed": 0, "errors": 0,
        })
    )
    with pytest.raises(WebclawError, match="unknown status"):
        await client.wait_for_crawl("aw", interval=0.01, timeout=5.0)


@respx.mock
async def test_async_poll_backoff_grows(client: AsyncWebclaw, monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    import webclaw.async_client as ac

    monkeypatch.setattr(ac.asyncio, "sleep", fake_sleep)

    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        status = "completed" if call["n"] >= 4 else "running"
        return httpx.Response(200, json={
            "id": "ab", "status": status,
            "pages": [], "total": 1, "completed": 0, "errors": 0,
        })

    respx.get(f"{BASE}/v1/crawl/ab").mock(side_effect=respond)
    await client.wait_for_crawl("ab", interval=1.0, timeout=1000.0)
    assert sleeps == [1.0, 1.5, 2.25]


# -- Fix 5: untested surface (async) ------------------------------------------


@respx.mock
async def test_search(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/search").mock(
        return_value=httpx.Response(200, json={"query": "q", "results": []})
    )
    out = await client.search("q", num_results=3)
    assert out["query"] == "q"


@respx.mock
async def test_diff(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/diff").mock(
        return_value=httpx.Response(200, json={"url": "https://x.com", "has_changed": False})
    )
    out = await client.diff("https://x.com")
    assert out["has_changed"] is False


@respx.mock
async def test_research_completes(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/research").mock(
        return_value=httpx.Response(200, json={"id": "ac", "status": "processing"})
    )
    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        if call["n"] < 2:
            return httpx.Response(200, json={"id": "ac", "status": "processing"})
        return httpx.Response(200, json={"id": "ac", "status": "completed", "report": "R"})

    respx.get(f"{BASE}/v1/research/ac").mock(side_effect=respond)
    res = await client.research("q")
    assert res.report == "R"


@respx.mock
async def test_wait_for_research(client: AsyncWebclaw):
    respx.get(f"{BASE}/v1/research/awr").mock(
        return_value=httpx.Response(200, json={"id": "awr", "status": "completed", "report": "ok"})
    )
    res = await client.wait_for_research("awr", interval=0.01, timeout=5.0)
    assert res.report == "ok"


@respx.mock
async def test_wait_for_crawl(client: AsyncWebclaw):
    respx.get(f"{BASE}/v1/crawl/awc").mock(
        return_value=httpx.Response(200, json={
            "id": "awc", "status": "completed",
            "pages": [{"url": "https://x.com", "markdown": "ok", "metadata": {}}],
            "total": 1, "completed": 1, "errors": 0,
        })
    )
    res = await client.wait_for_crawl("awc", interval=0.01, timeout=5.0)
    assert res.status == "completed"


@respx.mock
async def test_watch_crud(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/watch").mock(
        return_value=httpx.Response(200, json={"id": "aw1", "url": "https://x.com"})
    )
    respx.get(f"{BASE}/v1/watch").mock(
        return_value=httpx.Response(200, json={"watches": [{"id": "aw1", "url": "https://x.com"}], "total": 1})
    )
    respx.get(f"{BASE}/v1/watch/aw1").mock(
        return_value=httpx.Response(200, json={"id": "aw1", "url": "https://x.com"})
    )
    respx.post(f"{BASE}/v1/watch/aw1/check").mock(
        return_value=httpx.Response(200, json={"id": "aw1", "has_changed": True, "checked_at": "t"})
    )
    respx.delete(f"{BASE}/v1/watch/aw1").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )

    created = await client.watch_create("https://x.com")
    assert created.id == "aw1"
    listed = await client.watch_list()
    assert listed.total == 1
    got = await client.watch_get("aw1")
    assert got.id == "aw1"
    checked = await client.watch_check("aw1")
    assert checked.has_changed is True
    await client.watch_delete("aw1")


@respx.mock
async def test_scrape_youtube(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://youtu.be/q", "metadata": {}, "markdown": "v",
            "transcript": "t", "youtube": {"video_id": "vid", "title": "Y"},
        })
    )
    res = await client.scrape("https://youtu.be/q")
    assert res.transcript == "t"
    assert res.youtube is not None
    assert res.youtube.video_id == "vid"


@respx.mock
async def test_batch_full_shape(client: AsyncWebclaw):
    respx.post(f"{BASE}/v1/batch").mock(
        return_value=httpx.Response(200, json={
            "results": [
                {"url": "https://a.com", "markdown": "# A", "text": "A", "llm": "A llm",
                 "extraction": {"k": 1}, "metadata": {}},
            ]
        })
    )
    res = await client.batch(["https://a.com"])
    a = res.results[0]
    assert a.text == "A"
    assert a.llm == "A llm"
    assert a.json_data == {"k": 1}
