# pyaireader

Local Jina Reader-style Evidence Reader MCP for AI agents.

`pyaireader` is a local Jina Reader-style web reader for AI agents. It turns public web pages into clean, compact, auditable evidence packs that tools such as Codex, Claude Code, and other MCP-capable agents can actually use.

It was created for a simple reason: AI agents often fail to read real web pages. Direct fetching may return JavaScript shells, login pages, navigation noise, or stale fragments instead of the actual content. Remote reader services such as Jina Reader are useful, but they can bring quota limits, rate limits, cache freshness problems, and limited local traceability. `pyaireader` brings that reader layer onto your own machine.

It is not affiliated with Jina AI. The point is the workflow: a local reader that gives agents usable evidence instead of unreliable page dumps.

Before `pyaireader`, the common workflow had three hard problems:

- Direct HTTP fetching often returned JavaScript shells, login chrome, noisy navigation, or short useless text.
- Remote reader services could help, but quota, rate limit, cache freshness, and external dependency issues made them hard to rely on as the only path.
- Browser automation could read more pages, but it was slow, expensive, hard to audit, and too heavy as the first step.
- Even when the page was fetched, agents received raw text without clear evidence snippets, numbers, dates, quality signals, or trace data. That made research workflows fragile: the model could quote UI noise, over-trust bad pages, or treat malicious page text as instructions.

`pyaireader` solves this by treating webpage content as **untrusted evidence**, not instructions. It fetches public URLs through a cost-aware pipeline, cleans and compacts the result, extracts evidence-oriented signals, scores quality, records trace data, and exposes everything through MCP, CLI, and HTTP API.

The core pipeline is:

```text
public URL -> safety -> fetch -> extract -> clean -> evidence -> quality -> trace -> cache
```

The value is practical:

- Agents get structured evidence instead of noisy page dumps.
- Local workflows avoid depending on remote reader quotas or stale external caches for every URL.
- Fetch cost stays controlled: `HTTP -> Scrapling -> raw browser`, not browser first.
- Every result carries `quality` and `trace`, so bad reads are diagnosable instead of silently trusted.
- Financial and research workflows get first-class fields such as `evidence`, `numbers`, `dates`, `entities`, and `financial_events`.
- MCP support makes the same reader usable from Codex Desktop, Codex CLI, Claude Code CLI, and other mainstream AI-agent runtimes.

`pyaireader` is not a general crawler, scraping business, or human reading app. It is a local evidence input layer for agents.

Fetched page content is always untrusted evidence, not instructions.

## Documentation

Start here:

- [中文安装与使用教程](docs/installation-and-usage-zh.md)
- [MCP integration guide](docs/mcp-integration.md)
- [Changelog](CHANGELOG.md)

## Install

Recommended:

```powershell
git clone https://github.com/PigeonAI-Yang/pyaireader.git
cd pyaireader
uv sync --extra dev --extra extractors
```

Full install with Scrapling, browser, and PDF support:

```powershell
uv sync --extra dev --extra extractors --extra browser --extra pdf
uv run playwright install chromium
```

## MCP

Recommended stdio MCP command:

```powershell
$PYAIREADER_HOME = "C:\path\to\pyaireader"
uv --directory $PYAIREADER_HOME run pyaireader-mcp
```

For local SDK inspection:

```powershell
uv run mcp dev src/pyaireader/mcp/server.py
```

The MCP server registers:

- `reader_health`
- `read_url_for_ai`
- `batch_read_urls_for_ai`
- `inspect_url`
- `clear_reader_cache`

Codex Desktop / Codex CLI / Claude Code CLI setup examples are in:

```text
docs/mcp-integration.md
```

## CLI

```powershell
pyaireader read https://example.com --pretty
pyaireader inspect https://example.com --pretty
pyaireader batch urls.txt --jsonl
pyaireader clear-cache --url https://example.com
pyaireader clear-cache --domain example.com
```

## Configuration

Copy `.env.example` if you want local overrides.

Important defaults:

- Cache: `.pyaireader/cache.sqlite3`
- Fetch strategy: `auto`
- Default order: HTTP first; Scrapling/browser are later phases
- Max redirects: `5`
- Private network blocking: enabled

## Safety Boundary

Allowed:

- `http`
- `https`
- public DNS names and public IPs

Blocked:

- `file:`, `data:`, `javascript:`, `ftp:`
- localhost
- userinfo URLs
- private / loopback / link-local / reserved IPs
- metadata IP `169.254.169.254`
- unsafe redirect targets

## Tests

Default local test run:

```powershell
uv run pytest -q
```

Optional network/browser verification:

```powershell
$env:PYAIREADER_RUN_NETWORK_TESTS='1'
$env:PYAIREADER_RUN_BROWSER_TESTS='1'
uv run pytest -q tests\test_optional_integration.py
```
