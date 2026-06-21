# Project Rules

## Agent Skills

- For pyaireader usage, web reading, X/Twitter search, article/tweet collection, or MCP/CLI smoke tests, use the `$pyaireader` skill from `skills/pyaireader/SKILL.md`.
- Keep `skills/pyaireader/SKILL.md` as the general reader entry point and platform index. Put special-platform procedures under `skills/pyaireader/references/platforms/`.
- For logged-in or dynamic browser reads, use the dedicated `edge_cdp_profile` channel by default. It launches real Edge with pyaireader's own profile under `~/.pyaireader/edge-cdp-profiles/` and must not open tabs in the user's daily Edge windows.
- For X/Twitter collection, `edge_cdp_profile` is the standard path. First-time login must be treated as part of the workflow: open `browser-login` or `edge-cdp-profile-launch`, give the user enough time to log in, then run a real `search-platform x` smoke test.
- `persistent_profile` is a fallback/diagnostic path, not the X/Twitter standard path. Do not silently fall back to Playwright Chromium for X/Twitter work; if Edge is unavailable, report the browser configuration blocker.
- X platform collection must not silently downgrade to anonymous web search. If `search-platform x` or MCP `search_platform(platform="x")` cannot run with a user browser session, report the task as incomplete and state the exact browser-session blocker.

## Release And Changelog

- Shipped changes must not stay only under `## Unreleased`. Before commit or push, move them into a dated section: `## X.Y.Z - YYYY-MM-DD`.
- When a release section is added, keep release metadata aligned in `pyproject.toml`, `uv.lock`, `src/pyaireader/mcp/server.py`, and `docs/registry-server-json-candidate.json`.
- Do not edit old planning examples just because they mention an older version.
- Before reporting release work as complete, run:
  - `uv lock` if `pyproject.toml` version changed
  - `uv run python -c "from importlib.metadata import version; print(version('pyaireader'))"`
  - `git diff --check`
