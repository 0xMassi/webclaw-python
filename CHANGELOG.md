# Changelog

## Unreleased

- **Breaking:** Lead enrichment retired. `lead`, `lead_batch`, `get_lead_batch`, `wait_for_lead_batch` (sync and async) and the `Lead*` types are removed. Use `extract` with your own schema for structured page extraction.
