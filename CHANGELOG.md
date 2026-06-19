# Changelog

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
