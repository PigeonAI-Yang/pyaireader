# Changelog

## Unreleased

### Added

- Windows global CLI shim installer for calling `pyaireader` from any project directory.

### Changed

- Clarified MCP tool descriptions so Agents can recognize URL reading, UI noise removal, and key content extraction use cases.
- Documented the intended boundary between MCP for Agents, CLI for workflows, and HTTP API for application runtimes.

## 0.2.0 - 2026-06-19

### Added

- Stable public result schema versions for read, inspect, batch, and health responses.
- Short MCP tool names: `read_url` and `batch_read_urls`.
- Compatibility aliases: `read_url_for_ai` and `batch_read_urls_for_ai`.
- `reader_health` capability metadata for schemas, tools, defaults, safety, cache path, and transport.

### Changed

- Standardized failure payloads with `error.code`, `error.message`, `error.retryable`, and `error.suggested_next_action`.
- Updated MCP documentation to recommend short tool names while preserving old names for existing Agent configs.

## 0.1.0 - 2026-06-19

Initial public release.

### Added

- Local AI evidence reader pipeline for public URLs.
- CLI entry point: `pyaireader`.
- MCP stdio server entry point: `pyaireader-mcp`.
- HTTP API entry point: `pyaireader-api`.
- URL safety checks for scheme, userinfo, DNS resolution, private IPs, metadata IPs, and unsafe redirects.
- HTTP fetcher with manual redirect validation.
- Optional Scrapling and browser-backed fetchers.
- Optional PDF extraction.
- SQLite cache with quality-aware write policy.
- Evidence, number, date, entity, financial event, quality, and trace outputs.
- X/Twitter status extraction for cleaner single-post evidence.
- URL-aware number extraction to avoid treating URL digits as evidence numbers.
- Chinese installation and usage guide.
- MCP integration guide for Codex and Claude Code style agents.
