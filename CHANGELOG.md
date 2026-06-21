# Changelog

## 0.4.0 - 2026-06-21

### Added

- Platform adapter layer for site-specific readers, starting with X status and X Article URLs.
- `auth_strategy` support across CLI, MCP, HTTP API, and reader models:
  `anonymous`, `user_session_fallback`, and `user_session_only`.
- User-authorized local browser session layer with CDP and pyaireader-managed persistent profile providers.
- Explicit browser provider selection through `PYAIREADER_BROWSER_PROVIDER=auto/cdp/edge_cdp_profile/persistent_profile`.
- `pyaireader browser-status` and MCP/HTTP browser session status reporting, so users can see whether reads use CDP or pyaireader's persistent profile.
- `pyaireader browser-login x --provider edge_cdp_profile` for first-time login in the dedicated Edge-CDP profile, with `persistent_profile` kept as fallback.
- `pyaireader edge-cdp-launch` helper for launching Edge with a CDP port and printing the required pyaireader environment variables.
- `pyaireader edge-cdp-profile-launch` and `edge_cdp_profile` browser provider for a dedicated, persistent Edge-CDP profile on port 9334.
- X Article and X status user-session fallback when logged-out public content does not expose the readable body.
- X platform search/evidence collection through CLI, HTTP API, and MCP tools:
  `search_platform` and `collect_platform_evidence`.
- Trace fields for auth/session diagnostics: `auth_strategy`, `user_session_used`,
  `browser_provider`, `visited_urls`, and `user_task_scope`.
- Storage adapter layer that separates reading from saving user material.
- Stable `ReadingItem` schema: `pyaireader.reading_item.v1`.
- Default local SQLite library at `~/.pyaireader/library.sqlite3`.
- Filesystem storage backend that writes machine-readable JSON and optional Markdown.
- `~/.pyaireader/stores.toml` configuration for named stores.
- CLI library commands: `storage-status`, `library list`, `library get`, `library search`, and `library export`.
- MCP storage tools: `storage_status`, `save_reading_item`, `library_list`, `library_get`, and `library_search`.
- HTTP storage endpoints: `/v1/storage-status`, `/v1/library/list`, `/v1/library/get`, `/v1/library/search`, and `/v1/library/save`.
- Codex skill at `skills/pyaireader/SKILL.md` for repeatable pyaireader usage, platform workflow routing, login-state handling, and no-downgrade completion rules.
- X/Twitter platform procedure at `skills/pyaireader/references/platforms/x.md`.

### Changed

- Documented the boundary between reader cache and library/storage: cache is a temporary acceleration layer, while library/storage is the user material layer.
- Updated `read_url` MCP annotations to reflect that the tool can write to local storage when called with `save=true`.
- Kept SQLite as the default local store while documenting filesystem stores and future adapter directions instead of tying pyaireader to one project database.
- Browser provider `auto` now only checks the dedicated Edge-CDP profile endpoint `127.0.0.1:9334`; ordinary CDP endpoints require explicit `cdp` provider selection, and `auto` no longer silently opens pyaireader's managed persistent profile.
- CDP browser reads now create background targets by default, so X search/detail collection does not repeatedly steal focus from the user's active browser window.
- X platform search now ranks candidates by practical usefulness signals and exposes `usefulness_score` / `usefulness_signals` in item metrics.
- Agent-facing X collection workflow now treats the dedicated `edge_cdp_profile` channel as the standard path, with first-time login and smoke testing before collection.
- Agent-facing platform guidance now keeps the main skill as a general reader entry point and moves special-platform rules into indexed reference files.
- pyaireader-managed `persistent_profile` now launches Edge explicitly instead of Playwright's bundled Chromium, and reports Edge path details in browser status.
- Browser status and browser-login now expose X login-cookie diagnostics for the managed profile without reading cookie values.

### Fixed

- X status posts that only contain a short link to an X Article no longer return the short link as usable article text. If the article body is not available from public logged-out data, `read_url` now returns `success=false` with `x_article_body_not_extracted`.
- X Article logged-out shells are rejected as unreadable content instead of being cleaned into a false positive article body.
- `read_url(save=true)` can save successful cached reads without mixing request-specific storage fields into the reader cache.
- Raw browser and user-session browser reads work under MCP hosts that already own an asyncio loop by running sync Playwright operations in a browser worker thread.
- X platform search results are scored as short social evidence instead of being failed by long-article length thresholds.
- Authenticated X status and X Article extractors are scored as social primary content instead of being failed by login chrome.
- Reader eval corpus now covers positive HTML, PDF, X status, X Article, X search ranking, login shell, and JS shell cases.
- X platform workflow no longer allows silent Chromium fallback when Edge is unavailable.
- X search redirects to an X login page now fail as `x_login_required` instead of misleadingly reporting `platform_search_no_results`.

## 0.3.0 - 2026-06-20

### Added

- Windows global CLI shim installer for calling `pyaireader` from any project directory.
- Explicit MCP `outputSchema` through Pydantic boundary models.
- MCP `structuredContent` responses while keeping text JSON for older clients.
- MCP tool annotations for read-only, destructive, idempotent, and open-world behavior.
- `pyaireader-mcp-http` entry point for local MCP Streamable HTTP at `/mcp`.
- Registry metadata candidate for a future official registry submission.

### Changed

- Clarified MCP tool descriptions so Agents can recognize URL reading, UI noise removal, and key content extraction use cases.
- Documented the intended boundary between MCP for Agents, CLI for workflows, and HTTP API for application runtimes.
- Raised the MCP SDK dependency to the version family verified for structured output and Streamable HTTP.
- Renamed the internal local reader roadmap to avoid public-facing third-party brand positioning.

### Fixed

- Reduced false `login_required` quality failures when a normal long article contains only navigation/login chrome.

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
