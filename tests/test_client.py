"""Tests for the synchronous Webclaw client."""

import httpx
import pytest
import respx

from webclaw import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
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


# -- endpoints ----------------------------------------------------------------


@respx.mock
def test_endpoints_success_shape(client: Webclaw):
    respx.post(f"{BASE}/v1/endpoints").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "bundles_scanned": 3,
            "endpoint_count": 2,
            "endpoints": [
                {"value": "/api/users", "kind": "relative_path",
                 "first_party": True, "source": "main.js"},
                {"value": "wss://rt.example.com/socket", "kind": "web_socket",
                 "first_party": True, "source": "inline"},
            ],
            "hosts": ["example.com", "rt.example.com"],
            "truncated": False,
        })
    )
    res = client.endpoints("https://example.com")
    assert res.url == "https://example.com"
    assert res.bundles_scanned == 3
    assert res.endpoint_count == 2
    assert res.truncated is False
    assert res.hosts == ["example.com", "rt.example.com"]
    assert len(res.endpoints) == 2
    first = res.endpoints[0]
    assert first.value == "/api/users"
    assert first.kind == "relative_path"
    assert first.first_party is True
    assert first.source == "main.js"
    assert res.endpoints[1].kind == "web_socket"


@respx.mock
def test_endpoints_params_passthrough(client: Webclaw):
    route = respx.post(f"{BASE}/v1/endpoints").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com", "bundles_scanned": 0,
            "endpoint_count": 0, "endpoints": [], "hosts": [], "truncated": False,
        })
    )
    client.endpoints(
        "https://example.com", include_third_party=True, max_bundles=10,
    )
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["url"] == "https://example.com"
    assert payload["include_third_party"] is True
    assert payload["max_bundles"] == 10


@respx.mock
def test_endpoints_defaults_omitted_and_max_bundles_clamped(client: Webclaw):
    route = respx.post(f"{BASE}/v1/endpoints").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com", "bundles_scanned": 0,
            "endpoint_count": 0, "endpoints": [], "hosts": [], "truncated": False,
        })
    )
    # Defaults must be omitted entirely; over-cap max_bundles clamps to 20.
    client.endpoints("https://example.com")
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload == {"url": "https://example.com"}

    client.endpoints("https://example.com", max_bundles=999)
    payload = json.loads(route.calls.last.request.read())
    assert payload["max_bundles"] == 20


@respx.mock
def test_endpoints_400_invalid_url(client: Webclaw):
    respx.post(f"{BASE}/v1/endpoints").mock(
        return_value=httpx.Response(400, json={"error": "url is required"})
    )
    with pytest.raises(WebclawError, match="url is required") as exc:
        client.endpoints("not-a-url")
    assert exc.value.status_code == 400
    assert not isinstance(
        exc.value, (AuthenticationError, NotFoundError, RateLimitError)
    )


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


# -- lead ---------------------------------------------------------------------


@respx.mock
def test_lead(client: Webclaw):
    route = respx.post(f"{BASE}/v1/lead").mock(
        return_value=httpx.Response(200, json={
            "url": "https://posthog.com",
            "domain": "posthog.com",
            "lead": {
                "company_name": "PostHog",
                "summary": "Open-source product analytics.",
                "socials": {
                    "linkedin": "https://linkedin.com/company/posthog",
                    "x": "https://x.com/posthog",
                    "github": "https://github.com/PostHog",
                },
                "tech": ["Django", "React", "ClickHouse"],
                "pricing": [
                    {"plan": "Free", "price": "$0"},
                    {"plan": "Scale", "price": "$0.00005/event"},
                ],
                "emails": [
                    {"type": "support", "email": "hey@posthog.com"},
                    {"type": "sales", "email": "sales@posthog.com"},
                ],
                "people": [
                    {
                        "name": "James Hawkins",
                        "role": "CEO",
                        "linkedin": "https://linkedin.com/in/james-hawkins",
                        "x": "https://x.com/james406",
                    },
                    {"name": "Tim Glaser", "role": "CTO", "linkedin": None, "x": None},
                ],
            },
            "people_source": "team_page",
            "cache": "miss",
            "credits": 100,
        })
    )
    result = client.lead("https://posthog.com")

    # request was sent to /v1/lead with no depth
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload == {"url": "https://posthog.com"}

    # response parsed into typed dataclasses
    assert result.url == "https://posthog.com"
    assert result.domain == "posthog.com"
    assert result.lead.company_name == "PostHog"
    assert result.lead.summary == "Open-source product analytics."
    assert result.lead.socials.linkedin == "https://linkedin.com/company/posthog"
    assert result.lead.socials.github == "https://github.com/PostHog"
    assert result.lead.tech == ["Django", "React", "ClickHouse"]
    assert result.lead.pricing[1].plan == "Scale"
    assert result.lead.pricing[1].price == "$0.00005/event"
    assert result.lead.emails[0].type == "support"
    assert result.lead.emails[0].email == "hey@posthog.com"
    assert result.lead.people[0].name == "James Hawkins"
    assert result.lead.people[0].role == "CEO"
    assert result.lead.people[0].linkedin == "https://linkedin.com/in/james-hawkins"
    assert result.lead.people[0].x == "https://x.com/james406"
    assert result.lead.people[1].linkedin is None
    assert result.lead.people[1].x is None
    assert result.people_source == "team_page"
    assert result.cache == "miss"
    assert result.credits == 100


@respx.mock
def test_lead_omits_no_cache_by_default(client: Webclaw):
    route = respx.post(f"{BASE}/v1/lead").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com",
            "domain": "example.com",
            "lead": {},
            "people_source": "",
            "cache": "hit",
            "credits": 100,
        })
    )
    result = client.lead("https://example.com")

    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload == {"url": "https://example.com"}
    assert "no_cache" not in payload
    assert "depth" not in payload

    # an empty lead block still parses into a full LeadData with sane defaults
    assert result.lead.company_name is None
    assert result.lead.socials.github is None
    assert result.lead.tech == []
    assert result.lead.pricing == []
    assert result.lead.emails == []
    assert result.lead.people == []
    assert result.people_source == ""


@respx.mock
def test_lead_sends_no_cache_when_true(client: Webclaw):
    route = respx.post(f"{BASE}/v1/lead").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com", "domain": "example.com",
            "lead": {}, "cache": "miss", "credits": 100,
        })
    )
    client.lead("https://example.com", no_cache=True)
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["no_cache"] is True


# -- lead batch ---------------------------------------------------------------


@respx.mock
def test_lead_batch_start(client: Webclaw):
    route = respx.post(f"{BASE}/v1/lead/batch").mock(
        return_value=httpx.Response(200, json={
            "id": "lb-1", "status": "processing", "total": 2, "credits_per_url": 100,
        })
    )
    job = client.lead_batch(["https://posthog.com", "https://vercel.com"])
    assert job.id == "lb-1"
    assert job.status == "processing"
    assert job.total == 2
    assert job.credits_per_url == 100

    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload == {"urls": ["https://posthog.com", "https://vercel.com"]}
    assert "no_cache" not in payload


@respx.mock
def test_lead_batch_sends_no_cache_when_true(client: Webclaw):
    route = respx.post(f"{BASE}/v1/lead/batch").mock(
        return_value=httpx.Response(200, json={
            "id": "lb-2", "status": "processing", "total": 1, "credits_per_url": 100,
        })
    )
    client.lead_batch(["https://example.com"], no_cache=True)
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["no_cache"] is True


@respx.mock
def test_lead_batch_too_many_urls_400(client: Webclaw):
    respx.post(f"{BASE}/v1/lead/batch").mock(
        return_value=httpx.Response(400, json={"error": "at most 25 urls"})
    )
    with pytest.raises(WebclawError, match="at most 25 urls") as exc:
        client.lead_batch([f"https://ex{i}.com" for i in range(26)])
    assert exc.value.status_code == 400


@respx.mock
def test_lead_batch_insufficient_credits_402(client: Webclaw):
    respx.post(f"{BASE}/v1/lead/batch").mock(
        return_value=httpx.Response(402, json={"error": "insufficient credits"})
    )
    with pytest.raises(WebclawError, match="insufficient credits") as exc:
        client.lead_batch(["https://example.com"])
    assert exc.value.status_code == 402


@respx.mock
def test_get_lead_batch(client: Webclaw):
    respx.get(f"{BASE}/v1/lead/batch/lb-9").mock(
        return_value=httpx.Response(200, json={
            "id": "lb-9",
            "status": "completed",
            "total": 2,
            "completed": 2,
            "succeeded": 1,
            "credits_charged": 100,
            "results": [
                {
                    "url": "https://posthog.com",
                    "status": "success",
                    "domain": "posthog.com",
                    "cache": "miss",
                    "lead": {
                        "company_name": "PostHog",
                        "socials": {"github": "https://github.com/PostHog"},
                        "tech": ["Django", "ClickHouse"],
                        "pricing": [{"plan": "Free", "price": "$0"}],
                        "emails": [{"type": "support", "email": "hey@posthog.com"}],
                        "people": [
                            {"name": "James Hawkins", "role": "CEO",
                             "linkedin": "https://linkedin.com/in/james-hawkins", "x": None},
                        ],
                    },
                },
                {"url": "https://broken.example", "status": "error", "error": "unreachable"},
            ],
            "error": None,
            "created_at": "2026-07-18T10:00:00Z",
        })
    )
    status = client.get_lead_batch("lb-9")
    assert status.id == "lb-9"
    assert status.status == "completed"
    assert status.total == 2
    assert status.completed == 2
    assert status.succeeded == 1
    assert status.credits_charged == 100
    assert status.error is None
    assert status.created_at == "2026-07-18T10:00:00Z"
    assert len(status.results) == 2

    ok, bad = status.results
    assert ok.status == "success"
    assert ok.domain == "posthog.com"
    assert ok.cache == "miss"
    assert ok.lead is not None
    assert ok.lead.company_name == "PostHog"
    assert ok.lead.socials.github == "https://github.com/PostHog"
    assert ok.lead.tech == ["Django", "ClickHouse"]
    assert ok.lead.pricing[0].plan == "Free"
    assert ok.lead.emails[0].email == "hey@posthog.com"
    assert ok.lead.people[0].role == "CEO"
    assert ok.error is None

    assert bad.status == "error"
    assert bad.error == "unreachable"
    assert bad.lead is None


@respx.mock
def test_get_lead_batch_not_found_404(client: Webclaw):
    respx.get(f"{BASE}/v1/lead/batch/missing").mock(
        return_value=httpx.Response(404, json={"error": "job not found"})
    )
    with pytest.raises(NotFoundError, match="job not found"):
        client.get_lead_batch("missing")


@respx.mock
def test_wait_for_lead_batch(client: Webclaw):
    """wait_for_lead_batch should poll until status is 'completed'."""
    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        if call["n"] < 3:
            return httpx.Response(200, json={
                "id": "lb-w", "status": "processing",
                "total": 1, "completed": call["n"], "succeeded": 0,
                "credits_charged": 0, "results": [],
            })
        return httpx.Response(200, json={
            "id": "lb-w", "status": "completed",
            "total": 1, "completed": 1, "succeeded": 1, "credits_charged": 100,
            "results": [
                {"url": "https://a.com", "status": "success", "domain": "a.com",
                 "cache": "miss", "lead": {"company_name": "A"}},
            ],
        })

    respx.get(f"{BASE}/v1/lead/batch/lb-w").mock(side_effect=respond)
    status = client.wait_for_lead_batch("lb-w", interval=0.01, timeout=5.0)
    assert status.status == "completed"
    assert status.succeeded == 1
    assert status.results[0].lead.company_name == "A"
    assert call["n"] == 3


@respx.mock
def test_wait_for_lead_batch_failed_fails_fast(client: Webclaw):
    respx.get(f"{BASE}/v1/lead/batch/lb-f").mock(
        return_value=httpx.Response(200, json={
            "id": "lb-f", "status": "failed", "error": "billing error",
            "total": 1, "completed": 0, "succeeded": 0, "credits_charged": 0,
            "results": [],
        })
    )
    with pytest.raises(WebclawError, match="billing error"):
        client.wait_for_lead_batch("lb-f", interval=0.01, timeout=5.0)


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


# -- Fix 1: _raise_for_status robustness --------------------------------------


@respx.mock
def test_error_body_json_array_does_not_crash(client: Webclaw):
    """A JSON *array* error body has no .get(); must fall back to text,
    not raise AttributeError and mask the real 500."""
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(500, json=["boom", "stacktrace"])
    )
    with pytest.raises(WebclawError) as exc:
        client.scrape("https://example.com")
    assert exc.value.status_code == 500
    assert not isinstance(exc.value, (AuthenticationError, NotFoundError, RateLimitError))


@respx.mock
def test_error_body_json_string_does_not_crash(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(503, json="service unavailable")
    )
    with pytest.raises(WebclawError) as exc:
        client.scrape("https://example.com")
    assert exc.value.status_code == 503


@respx.mock
def test_error_body_json_number_does_not_crash(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(return_value=httpx.Response(500, json=42))
    with pytest.raises(WebclawError) as exc:
        client.scrape("https://example.com")
    assert exc.value.status_code == 500


@respx.mock
def test_error_body_json_dict_still_extracts_error(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(500, json={"error": "specific failure"})
    )
    with pytest.raises(WebclawError, match="specific failure"):
        client.scrape("https://example.com")


@respx.mock
def test_timeout_exception_mapped_to_sdk_error(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        side_effect=httpx.ConnectTimeout("timed out")
    )
    with pytest.raises(TimeoutError, match="timed out"):
        client.scrape("https://example.com")


@respx.mock
def test_transport_error_mapped_to_sdk_error(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    with pytest.raises(WebclawError) as exc:
        client.scrape("https://example.com")
    # Mapped to the SDK base error, not a leaked raw httpx exception.
    assert isinstance(exc.value, WebclawError)
    assert not isinstance(exc.value, httpx.HTTPError)
    assert "connection refused" in str(exc.value)


# -- Fix 2: poll backoff + terminal/unknown fail-fast -------------------------


@respx.mock
def test_research_failed_fails_fast(client: Webclaw):
    respx.post(f"{BASE}/v1/research").mock(
        return_value=httpx.Response(200, json={"id": "r-1"})
    )
    respx.get(f"{BASE}/v1/research/r-1").mock(
        return_value=httpx.Response(200, json={"id": "r-1", "status": "failed", "error": "llm down"})
    )
    with pytest.raises(WebclawError, match="llm down"):
        client.research("q", deep=False)


@respx.mock
def test_wait_for_crawl_interrupted_fails_fast(client: Webclaw):
    """An 'interrupted' crawl never reaches 'completed'; must raise
    immediately instead of polling until the timeout."""
    respx.get(f"{BASE}/v1/crawl/intr").mock(
        return_value=httpx.Response(200, json={
            "id": "intr", "status": "interrupted",
            "pages": [], "total": 0, "completed": 0, "errors": 0,
        })
    )
    with pytest.raises(WebclawError, match="failed"):
        client.wait_for_crawl("intr", interval=0.01, timeout=5.0)


@respx.mock
def test_unknown_status_fails_fast(client: Webclaw):
    """An unrecognised status must not spin until wall-clock timeout."""
    respx.get(f"{BASE}/v1/crawl/weird").mock(
        return_value=httpx.Response(200, json={
            "id": "weird", "status": "teleporting",
            "pages": [], "total": 0, "completed": 0, "errors": 0,
        })
    )
    with pytest.raises(WebclawError, match="unknown status"):
        client.wait_for_crawl("weird", interval=0.01, timeout=5.0)


@respx.mock
def test_poll_backoff_grows(client: Webclaw, monkeypatch):
    """Delay between polls should grow (capped), not stay flat at `interval`."""
    sleeps: list[float] = []
    import webclaw.client as wc

    monkeypatch.setattr(wc.time, "sleep", lambda s: sleeps.append(s))

    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        status = "completed" if call["n"] >= 5 else "running"
        return httpx.Response(200, json={
            "id": "b1", "status": status,
            "pages": [], "total": 1, "completed": 0, "errors": 0,
        })

    respx.get(f"{BASE}/v1/crawl/b1").mock(side_effect=respond)
    client.wait_for_crawl("b1", interval=1.0, timeout=1000.0)
    # 4 sleeps before the 5th (completed) poll; strictly increasing until cap.
    assert sleeps == [1.0, 1.5, 2.25, 3.375]


@respx.mock
def test_poll_backoff_capped(client: Webclaw, monkeypatch):
    sleeps: list[float] = []
    import webclaw.client as wc

    monkeypatch.setattr(wc.time, "sleep", lambda s: sleeps.append(s))

    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        status = "completed" if call["n"] >= 30 else "running"
        return httpx.Response(200, json={
            "id": "cap", "status": status,
            "pages": [], "total": 1, "completed": 0, "errors": 0,
        })

    respx.get(f"{BASE}/v1/crawl/cap").mock(side_effect=respond)
    client.wait_for_crawl("cap", interval=1.0, timeout=100000.0)
    assert max(sleeps) == wc._POLL_MAX_INTERVAL
    assert sleeps[-1] == wc._POLL_MAX_INTERVAL


# -- Fix 5: previously-untested surface ---------------------------------------


@respx.mock
def test_search(client: Webclaw):
    route = respx.post(f"{BASE}/v1/search").mock(
        return_value=httpx.Response(200, json={
            "query": "rust web scraping",
            "results": [{"title": "T", "url": "https://x.com", "description": "D"}],
        })
    )
    out = client.search("rust web scraping", num_results=5, topic="news")
    assert out["query"] == "rust web scraping"
    assert out["results"][0]["url"] == "https://x.com"
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["num_results"] == 5
    assert payload["topic"] == "news"


@respx.mock
def test_search_minimal_body(client: Webclaw):
    route = respx.post(f"{BASE}/v1/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client.search("q")
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload == {"query": "q"}


@respx.mock
def test_diff(client: Webclaw):
    route = respx.post(f"{BASE}/v1/diff").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com", "has_changed": True, "diff": "- old\n+ new",
        })
    )
    out = client.diff("https://example.com", granularity="line")
    assert out["has_changed"] is True
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["url"] == "https://example.com"
    assert payload["granularity"] == "line"


@respx.mock
def test_research_completes(client: Webclaw):
    respx.post(f"{BASE}/v1/research").mock(
        return_value=httpx.Response(200, json={"id": "rx", "status": "processing"})
    )
    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        if call["n"] < 2:
            return httpx.Response(200, json={"id": "rx", "status": "processing"})
        return httpx.Response(200, json={
            "id": "rx", "status": "completed", "query": "q",
            "report": "the report", "sources": [{"url": "https://s.com"}],
            "findings": [{"claim": "c"}], "iterations": 3, "elapsed_ms": 1200,
        })

    respx.get(f"{BASE}/v1/research/rx").mock(side_effect=respond)
    res = client.research("q")
    assert res.status == "completed"
    assert res.report == "the report"
    assert res.sources[0]["url"] == "https://s.com"
    assert res.iterations == 3


@respx.mock
def test_get_research_status(client: Webclaw):
    respx.get(f"{BASE}/v1/research/g1").mock(
        return_value=httpx.Response(200, json={
            "id": "g1", "status": "processing", "query": "q",
        })
    )
    res = client.get_research_status("g1")
    assert res.id == "g1"
    assert res.status == "processing"


@respx.mock
def test_wait_for_research(client: Webclaw):
    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        if call["n"] < 2:
            return httpx.Response(200, json={"id": "w9", "status": "processing"})
        return httpx.Response(200, json={
            "id": "w9", "status": "completed", "report": "done",
        })

    respx.get(f"{BASE}/v1/research/w9").mock(side_effect=respond)
    res = client.wait_for_research("w9", interval=0.01, timeout=5.0)
    assert res.report == "done"
    assert call["n"] == 2


# -- deprecated `deep` parameter ----------------------------------------------


def _mock_research_job(job_id: str):
    respx.post(f"{BASE}/v1/research").mock(
        return_value=httpx.Response(200, json={"id": job_id})
    )
    respx.get(f"{BASE}/v1/research/{job_id}").mock(
        return_value=httpx.Response(200, json={
            "id": job_id, "status": "completed", "report": "r",
        })
    )


@respx.mock
def test_research_deep_true_warns_and_still_forwards(client: Webclaw):
    """Explicit deep=True is deprecated: warn, but keep sending the field
    so older self-hosted servers that still honor it are unaffected."""
    import json

    _mock_research_job("dep1")
    with pytest.warns(DeprecationWarning, match="deep.*deprecated"):
        client.research("q", deep=True)
    sent = json.loads(respx.calls[0].request.read())
    assert sent["deep"] is True


@respx.mock
def test_research_default_no_warning_no_deep_field(client: Webclaw):
    """A caller relying on the default must not be warned, and the body
    must no longer carry the dead `deep` field."""
    import json
    import warnings as warnings_mod

    _mock_research_job("dep2")
    with warnings_mod.catch_warnings():
        warnings_mod.simplefilter("error", DeprecationWarning)
        client.research("q")
    sent = json.loads(respx.calls[0].request.read())
    assert "deep" not in sent


@respx.mock
def test_research_explicit_false_no_warning(client: Webclaw):
    """Explicit deep=False behaves exactly like the default: no warning,
    no `deep` field on the wire (the server ignores it either way)."""
    import json
    import warnings as warnings_mod

    _mock_research_job("dep3")
    with warnings_mod.catch_warnings():
        warnings_mod.simplefilter("error", DeprecationWarning)
        client.research("q", deep=False)
    sent = json.loads(respx.calls[0].request.read())
    assert "deep" not in sent


@respx.mock
def test_research_always_uses_deep_timeout(client: Webclaw, monkeypatch):
    """Every research job runs deep server-side (~20 min); a default caller
    must get the 1200s poll window, not the old 600s one."""
    import webclaw.client as wc

    captured: dict = {}

    def fake_poll(**kwargs):
        captured.update(kwargs)
        return "sentinel"

    monkeypatch.setattr(wc, "_poll_until_done", fake_poll)
    respx.post(f"{BASE}/v1/research").mock(
        return_value=httpx.Response(200, json={"id": "t1"})
    )
    assert client.research("q") == "sentinel"
    assert captured["timeout"] == 1200.0


@respx.mock
def test_wait_for_crawl(client: Webclaw):
    call = {"n": 0}

    def respond(request):
        call["n"] += 1
        if call["n"] < 2:
            return httpx.Response(200, json={
                "id": "c9", "status": "running",
                "pages": [], "total": 1, "completed": 0, "errors": 0,
            })
        return httpx.Response(200, json={
            "id": "c9", "status": "completed",
            "pages": [{"url": "https://x.com", "markdown": "ok", "metadata": {}}],
            "total": 1, "completed": 1, "errors": 0,
        })

    respx.get(f"{BASE}/v1/crawl/c9").mock(side_effect=respond)
    res = client.wait_for_crawl("c9", interval=0.01, timeout=5.0)
    assert res.status == "completed"
    assert res.pages[0].url == "https://x.com"


@respx.mock
def test_watch_create(client: Webclaw):
    route = respx.post(f"{BASE}/v1/watch").mock(
        return_value=httpx.Response(200, json={
            "id": "wch-1", "url": "https://example.com", "name": "my watch",
            "interval_minutes": 60, "status": "active", "created_at": "2026-01-01",
        })
    )
    w = client.watch_create(
        "https://example.com", name="my watch", interval_minutes=60,
        webhook_url="https://hook.example.com",
    )
    assert w.id == "wch-1"
    assert w.interval_minutes == 60
    assert w.status == "active"
    import json
    payload = json.loads(route.calls.last.request.read())
    assert payload["webhook_url"] == "https://hook.example.com"


@respx.mock
def test_watch_list(client: Webclaw):
    respx.get(f"{BASE}/v1/watch").mock(
        return_value=httpx.Response(200, json={
            "watches": [
                {"id": "a", "url": "https://a.com"},
                {"id": "b", "url": "https://b.com"},
            ],
            "total": 2,
        })
    )
    out = client.watch_list(limit=10, offset=0)
    assert out.total == 2
    assert out.watches[1].id == "b"


@respx.mock
def test_watch_get(client: Webclaw):
    respx.get(f"{BASE}/v1/watch/x1").mock(
        return_value=httpx.Response(200, json={"id": "x1", "url": "https://x.com"})
    )
    w = client.watch_get("x1")
    assert w.id == "x1"


@respx.mock
def test_watch_delete(client: Webclaw):
    route = respx.delete(f"{BASE}/v1/watch/d1").mock(
        return_value=httpx.Response(200, json={"deleted": True})
    )
    client.watch_delete("d1")
    assert route.called


@respx.mock
def test_watch_check(client: Webclaw):
    respx.post(f"{BASE}/v1/watch/c1/check").mock(
        return_value=httpx.Response(200, json={
            "id": "c1", "has_changed": True, "diff": "changed", "checked_at": "2026-01-02",
        })
    )
    res = client.watch_check("c1")
    assert res.has_changed is True
    assert res.diff == "changed"
    assert res.checked_at == "2026-01-02"


@respx.mock
def test_scrape_youtube_and_transcript(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://youtu.be/abc",
            "metadata": {},
            "markdown": "# Video",
            "transcript": "hello world transcript",
            "youtube": {
                "video_id": "abc12345678",
                "title": "Cool Video",
                "channel": "Chan",
                "duration_seconds": 212,
                "view_count": 9999,
                "tags": ["a", "b"],
                "categories": ["Education"],
            },
        })
    )
    res = client.scrape("https://youtu.be/abc")
    assert res.transcript == "hello world transcript"
    assert res.youtube is not None
    assert res.youtube.video_id == "abc12345678"
    assert res.youtube.title == "Cool Video"
    assert res.youtube.duration_seconds == 212
    assert res.youtube.tags == ["a", "b"]
    assert res.youtube.categories == ["Education"]


@respx.mock
def test_scrape_youtube_absent_is_none(client: Webclaw):
    respx.post(f"{BASE}/v1/scrape").mock(
        return_value=httpx.Response(200, json={
            "url": "https://example.com", "metadata": {}, "markdown": "x",
        })
    )
    res = client.scrape("https://example.com")
    assert res.youtube is None
    assert res.transcript is None


@respx.mock
def test_batch_full_shape(client: Webclaw):
    """parse_batch must surface text/llm/json/youtube/transcript, not drop them."""
    respx.post(f"{BASE}/v1/batch").mock(
        return_value=httpx.Response(200, json={
            "results": [
                {
                    "url": "https://a.com",
                    "markdown": "# A",
                    "text": "A plain",
                    "llm": "A for llm",
                    "extraction": {"k": "v"},
                    "metadata": {"title": "A"},
                },
                {
                    "url": "https://youtu.be/z",
                    "markdown": "# Z",
                    "transcript": "z transcript",
                    "youtube": {"video_id": "zzz", "title": "Z"},
                },
                {"url": "https://b.com", "error": "timeout"},
            ]
        })
    )
    res = client.batch(["https://a.com", "https://youtu.be/z", "https://b.com"])
    a, z, b = res.results
    assert a.text == "A plain"
    assert a.llm == "A for llm"
    assert a.json_data == {"k": "v"}
    assert z.transcript == "z transcript"
    assert z.youtube is not None
    assert z.youtube.video_id == "zzz"
    assert b.error == "timeout"
    assert b.youtube is None


def test_removed_dead_dataclasses_not_exported():
    """Honest public contract: the never-constructed wrappers are gone."""
    import webclaw

    for name in (
        "SearchResponse", "SearchResult", "DiffResponse",
        "ResearchStartResponse", "ResearchFinding", "ResearchSource",
    ):
        assert name not in webclaw.__all__
        assert not hasattr(webclaw, name)
