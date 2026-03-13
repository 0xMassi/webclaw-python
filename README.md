# webclaw

Python SDK for the [Webclaw](https://webclaw.io) web extraction API.

## Installation

```bash
pip install webclaw
```

## Quick Start

```python
from webclaw import Webclaw

client = Webclaw("wc_your_api_key")

# Scrape a page
result = client.scrape("https://example.com", formats=["markdown"])
print(result.markdown)
```

## Async Support

```python
from webclaw import AsyncWebclaw

async with AsyncWebclaw("wc_your_api_key") as client:
    result = await client.scrape("https://example.com", formats=["markdown"])
    print(result.markdown)
```

## API Reference

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
print(result.url)       # str
print(result.markdown)  # str | None
print(result.text)      # str | None
print(result.llm)       # str | None
print(result.metadata)  # dict
print(result.cache)     # CacheInfo | None
```

### Crawl

Start an async crawl job that follows links from a seed URL.

```python
job = client.crawl(
    "https://example.com",
    max_depth=3,
    max_pages=100,
    use_sitemap=True,
)

# Poll until complete
status = job.wait(interval=2.0, timeout=300.0)
for page in status.pages:
    print(page.url, len(page.markdown or ""))
```

Async crawl:

```python
job = await client.crawl("https://example.com")
status = await job.wait()
```

### Map

Discover URLs via sitemap parsing.

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
    print(item.url, item.error or "ok")
```

### Extract

LLM-powered structured data extraction.

```python
# Schema-based
result = client.extract(
    "https://example.com/pricing",
    schema={
        "type": "object",
        "properties": {
            "plans": {"type": "array", "items": {"type": "object"}}
        }
    },
)
print(result.data)

# Prompt-based
result = client.extract(
    "https://example.com",
    prompt="Extract all pricing tiers with names and prices",
)
print(result.data)
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

## Error Handling

```python
from webclaw.errors import (
    WebclawError,         # Base error
    AuthenticationError,  # 401/403
    NotFoundError,        # 404
    RateLimitError,       # 429
    TimeoutError,         # Request timeout
)

try:
    result = client.scrape("https://example.com")
except AuthenticationError:
    print("Invalid API key")
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

# Context manager for automatic cleanup
with Webclaw("wc_your_api_key") as client:
    result = client.scrape("https://example.com")
```

## Requirements

- Python 3.9+
- httpx

## License

MIT
