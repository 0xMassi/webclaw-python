"""Tests for the X (Twitter) monitoring endpoints on both clients.

Mirrors the watch tests: respx-mocked, asserting both the parsed response
shape and the outgoing request body (defaults omitted, filters passed
through, PATCH partial-update, cursor paging).
"""

import json

import httpx
import pytest
import respx

from webclaw import (
    AsyncWebclaw,
    AuthenticationError,
    Webclaw,
    XAudienceResponse,
    XMonitor,
    XMonitorListResponse,
)

BASE = "https://api.webclaw.io"


@pytest.fixture()
def client():
    c = Webclaw("test-key", base_url=BASE)
    yield c
    c.close()


@pytest.fixture()
async def aclient():
    c = AsyncWebclaw("test-key", base_url=BASE)
    yield c
    await c.close()


def _full_monitor(**overrides):
    base = {
        "id": "xm-1",
        "kind": "profile",
        "target": "elonmusk",
        "name": "Elon watch",
        "interval_minutes": 15,
        "webhook_url": "https://hooks.example.com/x",
        "active": True,
        "include_retweets": True,
        "include_replies": False,
        "include_quotes": True,
        "min_faves": 100,
        "keyword": "starship",
        "lang": "en",
        "last_checked_at": "2026-06-01T00:00:00Z",
        "last_matched_at": "2026-05-30T00:00:00Z",
        "created_at": "2026-05-01T00:00:00Z",
    }
    base.update(overrides)
    return base


# -- create -------------------------------------------------------------------


@respx.mock
def test_create_x_monitor_core_response(client: Webclaw):
    respx.post(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(200, json={
            "id": "xm-1", "kind": "search", "target": "web scraping",
            "name": "Scraping mentions", "interval_minutes": 30,
            "webhook_url": "https://hook.example.com", "active": True,
        })
    )
    m = client.create_x_monitor(
        "search", "web scraping", name="Scraping mentions",
        interval_minutes=30, webhook_url="https://hook.example.com",
    )
    assert isinstance(m, XMonitor)
    assert m.id == "xm-1"
    assert m.kind == "search"
    assert m.target == "web scraping"
    assert m.interval_minutes == 30
    assert m.active is True
    # Fields absent from the create response fall back to sensible defaults.
    assert m.min_faves == 0
    assert m.keyword is None


@respx.mock
def test_create_x_monitor_only_required_fields_in_body(client: Webclaw):
    route = respx.post(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(200, json={"id": "x", "kind": "profile", "target": "a"})
    )
    client.create_x_monitor("profile", "@handle")
    payload = json.loads(route.calls.last.request.read())
    # Only kind + target; every optional filter is omitted so the server
    # applies its own defaults (interval 15, min_faves 0, etc.).
    assert payload == {"kind": "profile", "target": "@handle"}


@respx.mock
def test_create_x_monitor_all_filters_passthrough(client: Webclaw):
    route = respx.post(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(200, json={"id": "x", "kind": "list", "target": "123"})
    )
    client.create_x_monitor(
        "list", "123", name="My list", interval_minutes=5,
        webhook_url="https://h", include_retweets=False, include_replies=False,
        include_quotes=False, min_faves=50, keyword="rust", lang="en",
    )
    payload = json.loads(route.calls.last.request.read())
    assert payload == {
        "kind": "list", "target": "123", "name": "My list",
        "interval_minutes": 5, "webhook_url": "https://h",
        "include_retweets": False, "include_replies": False,
        "include_quotes": False, "min_faves": 50, "keyword": "rust", "lang": "en",
    }


# -- list ---------------------------------------------------------------------


@respx.mock
def test_list_x_monitors(client: Webclaw):
    respx.get(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(200, json={
            "monitors": [_full_monitor(), _full_monitor(id="xm-2", kind="replies")],
        })
    )
    out = client.list_x_monitors(limit=10, offset=5)
    assert isinstance(out, XMonitorListResponse)
    assert len(out.monitors) == 2
    first = out.monitors[0]
    assert first.id == "xm-1"
    assert first.include_replies is False
    assert first.min_faves == 100
    assert first.keyword == "starship"
    assert first.last_matched_at == "2026-05-30T00:00:00Z"
    assert out.monitors[1].kind == "replies"


@respx.mock
def test_list_x_monitors_sends_pagination_params(client: Webclaw):
    route = respx.get(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(200, json={"monitors": []})
    )
    client.list_x_monitors(limit=25, offset=50)
    sent = route.calls.last.request
    assert sent.url.params["limit"] == "25"
    assert sent.url.params["offset"] == "50"


# -- get ----------------------------------------------------------------------


@respx.mock
def test_get_x_monitor(client: Webclaw):
    respx.get(f"{BASE}/v1/x/monitors/xm-1").mock(
        return_value=httpx.Response(200, json=_full_monitor())
    )
    m = client.get_x_monitor("xm-1")
    assert m.id == "xm-1"
    assert m.target == "elonmusk"
    assert m.include_quotes is True
    assert m.lang == "en"


# -- update -------------------------------------------------------------------


@respx.mock
def test_update_x_monitor_partial_body(client: Webclaw):
    route = respx.patch(f"{BASE}/v1/x/monitors/xm-1").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    client.update_x_monitor("xm-1", active=False, interval_minutes=60)
    payload = json.loads(route.calls.last.request.read())
    # PATCH must send only the fields the caller changed.
    assert payload == {"active": False, "interval_minutes": 60}


@respx.mock
def test_update_x_monitor_empty_when_nothing_set(client: Webclaw):
    route = respx.patch(f"{BASE}/v1/x/monitors/xm-1").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    client.update_x_monitor("xm-1")
    payload = json.loads(route.calls.last.request.read())
    assert payload == {}


# -- delete -------------------------------------------------------------------


@respx.mock
def test_delete_x_monitor(client: Webclaw):
    route = respx.delete(f"{BASE}/v1/x/monitors/xm-1").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    client.delete_x_monitor("xm-1")
    assert route.called


# -- check --------------------------------------------------------------------


@respx.mock
def test_check_x_monitor(client: Webclaw):
    route = respx.post(f"{BASE}/v1/x/monitors/xm-1/check").mock(
        return_value=httpx.Response(200, json={"status": "checking"})
    )
    result = client.check_x_monitor("xm-1")
    assert result is None
    assert route.called


# -- audience -----------------------------------------------------------------


@respx.mock
def test_export_x_audience_full_shape(client: Webclaw):
    respx.post(f"{BASE}/v1/x/audience").mock(
        return_value=httpx.Response(200, json={
            "user_id": "44196397",
            "direction": "followers",
            "count": 2,
            "users": [
                {"id": "1", "screen_name": "alice", "name": "Alice",
                 "followers": 1200, "description": "builder", "url": "https://a.co"},
                {"id": "2", "screen_name": "bob", "name": "Bob", "followers": 5},
            ],
            "next_cursor": "CURSOR_2",
            "pages_fetched": 2,
            "credits_charged": 2,
        })
    )
    res = client.export_x_audience(handle="@jack", max_pages=2)
    assert isinstance(res, XAudienceResponse)
    assert res.user_id == "44196397"
    assert res.direction == "followers"
    assert res.count == 2
    assert res.next_cursor == "CURSOR_2"
    assert res.pages_fetched == 2
    assert res.credits_charged == 2
    assert len(res.users) == 2
    assert res.users[0].screen_name == "alice"
    assert res.users[0].followers == 1200
    assert res.users[0].description == "builder"
    # Missing optional user fields default cleanly.
    assert res.users[1].description is None
    assert res.users[1].url is None


@respx.mock
def test_export_x_audience_body_omits_defaults(client: Webclaw):
    route = respx.post(f"{BASE}/v1/x/audience").mock(
        return_value=httpx.Response(200, json={"user_id": "1", "users": [], "next_cursor": None})
    )
    client.export_x_audience(handle="@jack")
    payload = json.loads(route.calls.last.request.read())
    assert payload == {"handle": "@jack"}


@respx.mock
def test_export_x_audience_paging_params_passthrough(client: Webclaw):
    route = respx.post(f"{BASE}/v1/x/audience").mock(
        return_value=httpx.Response(200, json={"user_id": "1", "users": [], "next_cursor": None})
    )
    client.export_x_audience(
        user_id="44196397", direction="following", cursor="C1", max_pages=5,
    )
    payload = json.loads(route.calls.last.request.read())
    assert payload == {
        "user_id": "44196397", "direction": "following",
        "cursor": "C1", "max_pages": 5,
    }


@respx.mock
def test_export_x_audience_null_cursor_means_done(client: Webclaw):
    respx.post(f"{BASE}/v1/x/audience").mock(
        return_value=httpx.Response(200, json={
            "user_id": "1", "direction": "followers", "count": 0,
            "users": [], "next_cursor": None, "pages_fetched": 1, "credits_charged": 1,
        })
    )
    res = client.export_x_audience(user_id="1", cursor="LAST")
    # None (not "") preserves the "audience fully walked" signal.
    assert res.next_cursor is None


# -- paid-only (403) ----------------------------------------------------------


@respx.mock
def test_create_x_monitor_403_is_auth_error(client: Webclaw):
    respx.post(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(403, json={"error": "X monitoring requires a paid plan"})
    )
    with pytest.raises(AuthenticationError, match="paid plan"):
        client.create_x_monitor("profile", "@handle")


# -- async mirror -------------------------------------------------------------


@respx.mock
async def test_async_x_monitor_crud(aclient: AsyncWebclaw):
    respx.post(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(200, json={
            "id": "axm-1", "kind": "profile", "target": "jack",
            "interval_minutes": 15, "active": True,
        })
    )
    respx.get(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(200, json={"monitors": [_full_monitor(id="axm-1")]})
    )
    respx.get(f"{BASE}/v1/x/monitors/axm-1").mock(
        return_value=httpx.Response(200, json=_full_monitor(id="axm-1"))
    )
    respx.patch(f"{BASE}/v1/x/monitors/axm-1").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    respx.post(f"{BASE}/v1/x/monitors/axm-1/check").mock(
        return_value=httpx.Response(200, json={"status": "checking"})
    )
    respx.delete(f"{BASE}/v1/x/monitors/axm-1").mock(
        return_value=httpx.Response(200, json={"success": True})
    )

    created = await aclient.create_x_monitor("profile", "@jack")
    assert created.id == "axm-1"
    listed = await aclient.list_x_monitors()
    assert listed.monitors[0].id == "axm-1"
    got = await aclient.get_x_monitor("axm-1")
    assert got.id == "axm-1"
    assert await aclient.update_x_monitor("axm-1", active=False) is None
    assert await aclient.check_x_monitor("axm-1") is None
    assert await aclient.delete_x_monitor("axm-1") is None


@respx.mock
async def test_async_export_x_audience(aclient: AsyncWebclaw):
    respx.post(f"{BASE}/v1/x/audience").mock(
        return_value=httpx.Response(200, json={
            "user_id": "1", "direction": "following", "count": 1,
            "users": [{"id": "9", "screen_name": "z", "name": "Z", "followers": 3}],
            "next_cursor": None, "pages_fetched": 1, "credits_charged": 1,
        })
    )
    res = await aclient.export_x_audience(handle="@z", direction="following")
    assert res.direction == "following"
    assert res.users[0].screen_name == "z"
    assert res.next_cursor is None


@respx.mock
async def test_async_create_x_monitor_403(aclient: AsyncWebclaw):
    respx.post(f"{BASE}/v1/x/monitors").mock(
        return_value=httpx.Response(403, json={"error": "paid only"})
    )
    with pytest.raises(AuthenticationError):
        await aclient.create_x_monitor("search", "rust")
