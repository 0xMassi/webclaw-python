<p align="center">
  <a href="https://webclaw.io">
    <img src=".github/banner.png" alt="webclaw" width="600" />
  </a>
</p>

<p align="center">
  <strong>Python SDK for the Webclaw web extraction API</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/webclaw"><img src="https://img.shields.io/pypi/v/webclaw?style=flat-square&color=212529" alt="PyPI" /></a>
  <a href="https://pypi.org/project/webclaw"><img src="https://img.shields.io/pypi/pyversions/webclaw?style=flat-square&color=212529" alt="Python" /></a>
  <a href="https://github.com/0xMassi/webclaw-python/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-212529?style=flat-square" alt="License" /></a>
</p>

---

## Installation

```bash
pip install webclaw
```

## Quick Start

```python
from webclaw import Webclaw

client = Webclaw("wc_your_api_key")

result = client.scrape("https://example.com", formats=["markdown"])
print(result.markdown)
```

### Async

```python
from webclaw import AsyncWebclaw

async with AsyncWebclaw("wc_your_api_key") as client:
    result = await client.scrape("https://example.com", formats=["markdown"])
    print(result.markdown)
```

## Endpoints

### Scrape

Extract content from a single URL.

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
result.metadata   # dict
result.cache      # CacheInfo | None
```

### Crawl

Start an async crawl that follows links from a seed URL.

```python
job = client.crawl("https://example.com", max_depth=3, max_pages=100, use_sitemap=True)

# Poll until complete
status = job.wait(interval=2.0, timeout=300.0)

for page in status.pages:
    print(page.url, len(page.markdown or ""))
```

Async variant:

```python
job = await client.crawl("https://example.com")
status = await job.wait()
```

### Map

Discover URLs via sitemap.

```python
result = client.map("https://example.com")
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
    print(item.url, item.error or "ok")
```

### Extract

LLM-powered structured data extraction.

```python
# Schema-based
result = client.extract(
    "https://example.com/pricing",
    schema={"type": "object", "properties": {"plans": {"type": "array"}}},
)

# Prompt-based
result = client.extract(
    "https://example.com",
    prompt="Extract all pricing tiers with names and prices",
)
```

### Summarize

```python
result = client.summarize("https://example.com", max_sentences=3)
print(result.summary)
```

### Brand

Extract brand identity (colors, fonts, logos).

```python
result = client.brand("https://example.com")
print(result.data)
```

### Search

Web search with optional scraping of results.

```python
results = client.search("web scraping tools 2026")
for r in results["results"]:
    print(r["title"], r["url"])
```

### Research

Start an async deep research job and poll for results.

```python
# Start a research job
result = client.research("How do modern web crawlers handle JS rendering?", max_sources=15, deep=True)
print(result.id, result.status)

# Poll for results
status = client.get_research_status(result.id)
print(status.report)
```

## Error Handling

```python
from webclaw.errors import (
    WebclawError,         # Base
    AuthenticationError,  # 401/403
    NotFoundError,        # 404
    RateLimitError,       # 429
    TimeoutError,         # Timeout
)

try:
    result = client.scrape("https://example.com")
except RateLimitError:
    print("Too many requests")
except WebclawError as e:
    print(f"API error: {e}")
```

## Configuration

```python
client = Webclaw(
    "wc_your_api_key",
    base_url="https://api.webclaw.io",  # default
    timeout=60.0,                        # seconds, default 30
)

# Context manager
with Webclaw("wc_your_api_key") as client:
    result = client.scrape("https://example.com")
```

## Requirements

- Python 3.9+
- [httpx](https://www.python-httpx.org/)

## License

MIT
