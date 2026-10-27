# CLAUDE.md

This file provides guidance to coding agents working in this repository.

`webclaw` on PyPI: the Python SDK for the hosted Webclaw REST API (`https://api.webclaw.io`). One runtime dependency (`httpx`), Python 3.9–3.13, hatchling build. The workspace `../CLAUDE.md` covers the API itself and the platform around it.

## Commands

Homebrew's system Python is externally managed and has no pytest, so work in a venv. The `[dev]` extra is required: plain `pip install -e .` installs no test tooling.

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # or: uv venv && uv pip install -e '.[dev]'
.venv/bin/pytest                                        # full suite (~5s, all mocked, no network)
.venv/bin/pytest tests/test_client.py::test_scrape_basic   # single test
.venv/bin/pytest -k x_monitor                           # by name pattern
```

CI (`.github/workflows/ci.yml`) runs only `pytest`, on Python 3.9 and 3.13, on pushes to `main` and on PRs. No linter, formatter, or type checker is configured. Code must still run on 3.9: every module uses `from __future__ import annotations` so `X | None` hints work there. Don't use runtime-evaluated 3.10+ syntax such as `match` or `|` in `isinstance`.

## Architecture

Three modules split every endpoint, so sync and async can't drift:

- **`webclaw/_endpoints.py`**: all transport-free logic. `build_*_body()` turns kwargs into the JSON body. `parse_*()` turns a response dict into a dataclass. It also holds the route constants and the job-state vocabulary (`SUCCESS_STATE`, `FAILURE_STATES`, `IN_PROGRESS_STATES`).
- **`webclaw/client.py`**: `Webclaw` (sync httpx). Each method is `build → self._request → parse`. It also owns the shared private helpers: `_raise_for_status`, `_decode_json_body`, and the poll-loop pieces.
- **`webclaw/async_client.py`**: `AsyncWebclaw`, a method-for-method mirror that **imports those private helpers from `client.py`**. The poll loop is the only duplicated code (`_async_poll_until_done`), because sleeping differs. A change to `_poll_until_done` must be copied there.

**Adding or changing an endpoint touches:** a builder and a parser in `_endpoints.py`, the response dataclass in `types.py`, the same method in both clients, exports in `__init__.py` (both the import list and `__all__`), tests for sync (`test_client.py`) and async (`test_async_client.py`), and the README section. The workspace rule is that all three SDKs (`../sdk-js`, `../sdk-go`) expose identical endpoints, and docstrings cross-reference their equivalents.

### Conventions baked into the code

- **Body builders omit anything left at its default** (`None`, `False`, or the server default). That way the server applies its own default and a PATCH stays partial. Add new optional params the same way. Don't send an explicit `null` or `false`.
- **Parsers are tolerant, with one exception.** Optional fields use `.get()` with a default, and nested lists/objects are `isinstance`-guarded. Fields the SDK can't work without go through `_require()`, which raises `WebclawError("Malformed … response")` instead of a bare `KeyError`. Nested types use a `from_dict` static method (lead, watch, X, endpoints).
- **Some endpoints return raw JSON on purpose:** `search` (typed as the `SearchResponse` TypedDict), `diff`, `list_extractors`, `scrape_vertical`.
- **Errors** (`errors.py`): 401/403 → `AuthenticationError` (paid-only X endpoints return 403 too), 404 → `NotFoundError`, 429 → `RateLimitError`, everything else → `WebclawError(status_code=…)`. The error body may be non-JSON or a non-object, and `_raise_for_status` falls back to the raw text. `webclaw.TimeoutError` deliberately shadows the builtin. It covers both httpx request timeouts and poll deadlines. Empty and 204 bodies decode to `None`.
- **Polling** (crawl, research, lead batch): delay starts at `interval` and grows ×1.5 up to a 15s cap. It tolerates 5 *consecutive* transient failures (timeout, 429, 5xx) and re-raises any other 4xx at once. A status outside the known sets **fails fast** instead of looping until the timeout. `research()` always polls for up to 1200s.
- **Deprecated kwargs stay accepted:** `research(deep=…)` and `search(topic=…)` emit `DeprecationWarning` (`stacklevel=2`). They are forwarded on the wire only when set, for older self-hosted servers.

## Tests

`respx` mocks httpx against `BASE = "https://api.webclaw.io"`. Tests assert on both the parsed result and the sent body (`json.loads(route.calls.last.request.read())`). The "omitted when default" behaviour is tested explicitly, so keep it covered. `asyncio_mode = "auto"` is set, so async tests need no marker. `tests/test_x.py` holds the sync and async tests for the X endpoints together.

## Release

The version lives only in `pyproject.toml`, and a release is a commit that bumps it (e.g. `chore: release 0.5.0 (…)`). The repo has no publish workflow: `dist/` is built locally and is gitignored. `.env` is also gitignored, and nothing in the code or tests reads it.
