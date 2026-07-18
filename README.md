<p align="center">
  <a href="https://webclaw.io">
    <img src=".github/banner.png" alt="webclaw" width="760" />
  </a>
</p>

<p align="center">
  <strong>Python SDK for the Webclaw web extraction API</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/webclaw"><img src="https://shieldcn.dev/pypi/v/webclaw.svg?variant=branded" alt="PyPI" /></a>
  <a href="https://pypi.org/project/webclaw"><img src="https://shieldcn.dev/pypi/pyversions/webclaw.svg?variant=branded" alt="Python versions" /></a>
  <a href="https://github.com/0xMassi/webclaw-python/stargazers"><img src="https://shieldcn.dev/github/stars/0xMassi/webclaw-python.svg?variant=branded&logo=github" alt="Stars" /></a>
  <a href="https://github.com/0xMassi/webclaw-python/blob/main/LICENSE"><img src="https://shieldcn.dev/github/license/0xMassi/webclaw-python.svg?variant=branded" alt="License" /></a>
</p>

---

> **Note**: The webclaw Cloud API is public. Create an API key at [webclaw.io](https://webclaw.io) or use the [open-source CLI/MCP](https://github.com/0xMassi/webclaw) for local extraction.

---

## Installation

```bash
pip install webclaw
```

Requires Python 3.9+. The only dependency is [httpx](https://www.python-httpx.org/).

## Quick Start

### Sync

```python
from webclaw import Webclaw

client = Webclaw("wc-YOUR_API_KEY")

result = client.scrape("https://example.com", formats=["markdown"])
print(result.markdown)
```

### Async

```python
from webclaw import AsyncWebclaw

async with AsyncWebclaw("wc-YOUR_API_KEY") as client:
    result = await client.scrape("https://example.com", formats=["markdown"])
    print(result.markdown)
```

Both clients support identical method signatures. Every sync method has an async equivalent. The examples below use the sync client for brevity.

## Endpoints

### Scrape

Extract content from a single URL. Supports multiple output formats: `"markdown"`, `"text"`, `"llm"`, `"json"`.

```python
result = client.scrape(
    "https://example.com",
    formats=["markdown", "text", "llm"],
    include_selectors=["article", ".content"],
    exclude_selectors=["nav", "footer"],
    only_main_content=True,
    no_cache=True,
)

result.url        # str
result.markdown   # str | None
result.text       # str | None
result.llm        # str | None
result.json_data  # Any | None
result.metadata   # dict
result.cache      # CacheInfo | None  (.status: "hit" | "miss" | "bypass")
result.warning    # str | None
```

### Vertical extractors

28 site-specific extractors that return typed JSON (GitHub, Reddit, Amazon, YouTube, PyPI, HuggingFace, Trustpilot, etc.) instead of generic markdown. See the [catalog](https://webclaw.io/docs/api/vertical) for the full list.

```python
# Discover available extractors
catalog = client.list_extractors()
for e in catalog["extractors"]:
    print(e["name"], "-", e["label"])

# Run a specific extractor
pr = client.scrape_vertical(
    "github_pr",
    "https://github.com/rust-lang/rust/pull/123456",
)
print(pr["data"])  # {title, state, author, commits, reviews, ...}

# Amazon product as typed JSON
product = client.scrape_vertical(
    "amazon_product",
    "https://www.amazon.com/dp/B0C6KKQ7ND",
)
print(product["data"]["price"], product["data"]["rating"])
```

The `data` field is extractor-specific; call `list_extractors()` to discover what each returns. Both methods have async equivalents on `AsyncWebclaw`.

### Search

Web search with optional topic filtering.

```python
results = client.search("web scraping tools 2026", num_results=10, topic="tech")

for r in results["results"]:
    print(r["title"], r["url"])
```

**Parameters:** `query` (str), `num_results` (int, optional), `topic` (str, optional).

### Map

Discover URLs via sitemap.

```python
result = client.map("https://example.com")

print(result.count)
for url in result.urls:
    print(url)
```

### Batch

Scrape multiple URLs in parallel.

```python
result = client.batch(
    ["https://a.com", "https://b.com", "https://c.com"],
    formats=["markdown"],
    concurrency=5,
)

for item in result.results:
    print(item.url, item.markdown, item.error or "ok")
```

**Parameters:** `urls` (list[str]), `formats` (optional), `concurrency` (int, default 5).

### Endpoints

Discover the API endpoints a page calls at runtime by scanning its inline JavaScript and external `<script src>` bundles. This surfaces the routes a single-page app hits that `map` (sitemap-based) can't see: relative paths, absolute URLs, GraphQL operations, and WebSocket endpoints.

```python
result = client.endpoints(
    "https://app.example.com",
    include_third_party=False,  # default: skip analytics/CDN hosts
    max_bundles=20,             # default & server max: external scripts to scan
)

print(result.bundles_scanned, result.endpoint_count, result.truncated)
print(result.hosts)  # list[str] of hosts seen across endpoints

for e in result.endpoints:
    print(e.kind, e.value, "first-party" if e.first_party else "third-party", "via", e.source)
```

Each endpoint's `kind` is one of `"relative_path"`, `"absolute_url"`, `"graph_ql"`, `"web_socket"` (the values in `EndpointKind`). `truncated` is `True` when more bundles existed than `max_bundles` allowed.

**Parameters:** `url` (str), `include_third_party` (bool, default False), `max_bundles` (int, default 20, capped at 20).

### Extract

LLM-powered structured data extraction. Use either a JSON schema or a natural language prompt.

```python
# Schema-based extraction
result = client.extract(
    "https://example.com/pricing",
    schema={
        "type": "object",
        "properties": {
            "plans": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "price": {"type": "string"},
                    },
                },
            }
        },
    },
)
print(result.data)  # dict matching your schema

# Prompt-based extraction
result = client.extract(
    "https://example.com/pricing",
    prompt="Extract all pricing tiers with names and monthly prices",
)
print(result.data)
```

### Lead Enrichment API

Enrich a company from its website into a structured lead: company name,
summary, socials, tech stack, pricing, emails, and people (each with optional
LinkedIn / X profile URLs). Flat **100 credits per successful lead**.

```python
result = client.lead("https://resend.com")

print(result.domain)                 # "resend.com"
print(result.lead.company_name)      # "Resend"
print(result.lead.summary)           # "Email API for developers."
print(result.lead.socials.github)    # "https://github.com/resend"
print(result.lead.tech)              # ["Next.js", "React", "Vercel", ...]

for plan in result.lead.pricing:
    print(plan.plan, plan.price)     # LeadPricingPlan(plan=..., price=...)

for email in result.lead.emails:
    print(email.type, email.email)   # LeadEmail(type="support", email="...")

for person in result.lead.people:
    print(person.name, person.role)  # LeadPerson(name=..., role=...)
    print(person.linkedin, person.x) # profile URLs, or None if absent

print(result.people_source)          # e.g. "team_page"
print(result.cache)                  # "hit" | "miss"
print(result.credits)                # 100
```

### Summarize

Summarize page content with an optional sentence limit.

```python
result = client.summarize("https://example.com", max_sentences=3)
print(result.summary)
```

### Diff

Detect content changes at a URL since the last check.

```python
result = client.diff("https://example.com/status")

print(result["has_changed"])  # bool
print(result["diff"])         # str, unified diff of changes
```

### Brand

Extract brand identity (colors, fonts, logos) from a URL.

```python
result = client.brand("https://example.com")
print(result.data)  # dict with brand identity fields
```

### Research

Deep research that searches, reads, and synthesizes information from multiple sources. This is an async job: the SDK starts it and polls until completion.

```python
# Blocks until research completes (up to 600s, or 1200s with deep=True)
result = client.research(
    "How do modern web crawlers handle JavaScript rendering?",
    max_sources=15,
    deep=True,
    topic="tech",
)

print(result.report)
print(result.iterations)
print(result.elapsed_ms)

for source in result.sources:
    print(source["url"], source["title"])
```

To check status without blocking:

```python
status = client.get_research_status("job-id-here")
print(status.status)  # "running" | "completed" | "failed"
```

**Parameters:** `query` (str), `deep` (bool, default False), `max_sources` (int, optional), `max_iterations` (int, optional), `topic` (str, optional).

### Crawl

Start an async crawl that follows links from a seed URL.

```python
job = client.crawl(
    "https://example.com",
    max_depth=3,
    max_pages=100,
    use_sitemap=True,
)

# Poll until complete (default timeout 300s)
status = job.wait(interval=2.0, timeout=300.0)

print(status.total, status.completed, status.errors)
for page in status.pages:
    print(page.url, len(page.markdown or ""))
```

Check status without waiting:

```python
status = job.get_status()
print(status.status)  # "running" | "completed" | "failed"
```

Async variant:

```python
job = await client.crawl("https://example.com", max_depth=2)
status = await job.wait()
```

### Watch

Monitor URLs for content changes with automatic periodic checks.

**Create a watch:**

```python
watch = client.watch_create(
    "https://example.com/pricing",
    name="Pricing page monitor",
    interval_minutes=60,
    webhook_url="https://hooks.example.com/webclaw",
)
print(watch.id, watch.status)
```

**List all watches:**

```python
result = client.watch_list(limit=50, offset=0)
for w in result.watches:
    print(w.id, w.url, w.name, w.last_checked)
print(result.total)
```

**Get a single watch:**

```python
watch = client.watch_get("watch-id-here")
print(watch.url, watch.interval_minutes)
```

**Delete a watch:**

```python
client.watch_delete("watch-id-here")
```

**Trigger an immediate check:**

```python
check = client.watch_check("watch-id-here")
print(check.has_changed)  # bool
print(check.diff)         # str | None
print(check.checked_at)   # ISO timestamp
```

### X (Twitter) monitoring

Monitor X for new tweets matching a profile, search, list, or reply thread, and fire a webhook on new matches — plus export an account's followers or following. These are **paid-only** features (a free/lapsed account gets `AuthenticationError` for 403). Monitors and audience export are billed per X request at your plan rate (Starter 5, Growth 3, Pro 2, Scale 1 credits). Max 50 monitors per user.

**Create a monitor:**

```python
monitor = client.create_x_monitor(
    "search",                 # "profile" | "search" | "list" | "replies"
    "web scraping",           # handle / search query / list id / tweet id (per kind)
    name="Scraping mentions",
    interval_minutes=15,      # default 15, clamped 2..10080
    webhook_url="https://hooks.example.com/x",
    include_retweets=True,    # defaults: retweets/replies/quotes all True
    include_replies=False,
    include_quotes=True,
    min_faves=50,             # minimum likes to match (default 0)
    keyword="rust",           # only match tweets containing this
    lang="en",                # only match this language code
)
print(monitor.id, monitor.kind, monitor.active)
```

Only `kind` and `target` are required; every other argument is omitted from the request when left unset, so the server applies its own default.

**List monitors** (each is a full monitor object):

```python
result = client.list_x_monitors(limit=50, offset=0)
for m in result.monitors:
    print(m.id, m.kind, m.target, m.last_matched_at, m.active)
```

**Get, update, delete, and check:**

```python
m = client.get_x_monitor("monitor-id")

# PATCH — only the fields you pass are changed
client.update_x_monitor("monitor-id", active=False, interval_minutes=60)

client.delete_x_monitor("monitor-id")

# Trigger an immediate check (runs in the background; billed at your plan rate)
client.check_x_monitor("monitor-id")
```

**Webhook payload** posted to `webhook_url` on a match (Discord/Slack URLs get native formatting instead):

```json
{
  "event": "x.monitor.matched",
  "monitor_id": "xm-1", "kind": "search", "target": "web scraping",
  "new_count": 1,
  "tweets": [
    {
      "id": "...", "screen_name": "...", "text": "...", "url": "...",
      "created_at": "...", "favorite_count": 12, "retweet_count": 3,
      "reply_count": 1, "lang": "en", "is_retweet": false,
      "is_reply": false, "is_quote": false
    }
  ],
  "checked_at": "..."
}
```

**Export an audience** (followers or following), cursor-paginated and metered per page at your plan rate (Starter 5, Growth 3, Pro 2, Scale 1 credits):

```python
# Provide handle OR user_id. A pre-resolved user_id skips the (unbilled)
# re-resolve on later pages.
page = client.export_x_audience(
    handle="@jack",
    direction="followers",   # "followers" (default) | "following"
    max_pages=2,             # default 2, clamped 1..10 (~1-2k users/page)
)

for u in page.users:
    print(u.screen_name, u.name, u.followers, u.description)

print(page.pages_fetched, page.credits_charged)

# Walk the full audience: keep paging until next_cursor is None.
user_id, cursor = page.user_id, page.next_cursor
while cursor is not None:
    page = client.export_x_audience(user_id=user_id, cursor=cursor)
    # ... process page.users ...
    cursor = page.next_cursor
```

Every X method has an async equivalent on `AsyncWebclaw` with identical parameters.

## Error Handling

All errors inherit from `WebclawError`, which carries the HTTP status code when available.

```python
from webclaw import (
    WebclawError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    TimeoutError,
)

try:
    result = client.scrape("https://example.com")
except AuthenticationError:
    print("Invalid or missing API key")
except RateLimitError:
    print("Too many requests, slow down")
except NotFoundError:
    print("Resource not found")
except TimeoutError as e:
    print(f"Operation timed out: {e}")
except WebclawError as e:
    print(f"API error (status {e.status_code}): {e}")
```

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `AuthenticationError` | 401 / 403 | Invalid or missing API key |
| `NotFoundError` | 404 | Resource does not exist |
| `RateLimitError` | 429 | Too many requests |
| `TimeoutError` | -- | Crawl/research polling exceeded timeout |
| `WebclawError` | Any | Base class for all other API errors |

## Configuration

```python
import os
from webclaw import Webclaw

client = Webclaw(
    os.environ["WEBCLAW_API_KEY"],
    base_url="https://api.webclaw.io",  # default
    timeout=60.0,                        # seconds, default 30
)
```

Both `Webclaw` and `AsyncWebclaw` support context managers for automatic cleanup:

```python
# Sync
with Webclaw("wc-YOUR_API_KEY") as client:
    result = client.scrape("https://example.com")

# Async
async with AsyncWebclaw("wc-YOUR_API_KEY") as client:
    result = await client.scrape("https://example.com")
```

## Async Usage

Every endpoint is available on `AsyncWebclaw` with identical parameters. Use `await` on all method calls and `async with` for the context manager.

```python
import asyncio
from webclaw import AsyncWebclaw

async def main():
    async with AsyncWebclaw("wc-YOUR_API_KEY") as client:
        # Run multiple scrapes concurrently
        results = await asyncio.gather(
            client.scrape("https://a.com", formats=["markdown"]),
            client.scrape("https://b.com", formats=["markdown"]),
            client.scrape("https://c.com", formats=["markdown"]),
        )
        for r in results:
            print(r.url, len(r.markdown or ""))

asyncio.run(main())
```

## Type Support

This package ships with a `py.typed` marker (PEP 561). Type checkers like mypy and pyright will pick up all type annotations automatically. All response types are dataclasses importable from the top-level package:

```python
from webclaw import (
    ScrapeResponse, CrawlStatus, MapResponse, ExtractResponse, EndpointsResponse,
    LeadResponse, XMonitor, XMonitorListResponse, XAudienceResponse, XAudienceUser,
)
```

## License

MIT
