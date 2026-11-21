# Changelog

## Unreleased

- `WebclawError` (and every subclass) now has `request_id: Optional[str]`, read from the `x-request-id` response header or the error body's `request_id`. When present, `str(error)` ends with `(request id: <id>)`. This changes the error text: code that compares error messages exactly, or snapshot tests of them, needs updating.
- **Breaking (type):** `ScrapeResponse.actions_performed` is now `list[ActionResult]` (`action`, `success`, `error`), parsed from the API response. It was typed as an int, which never matched a real response.
- **Breaking:** Lead enrichment retired. `lead`, `lead_batch`, `get_lead_batch`, `wait_for_lead_batch` (sync and async) and the `Lead*` types are removed. Use `extract` with your own schema for structured page extraction.
