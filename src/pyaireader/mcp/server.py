from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pyaireader.config import ReaderConfig
from pyaireader.models import BatchReadUrlsRequest, InspectUrlRequest, ReadUrlRequest
from pyaireader.reader import ReaderPipeline


FetchStrategyArg = Literal["auto", "http_only", "scrapling_first", "browser_first", "browser_only"]
ReturnFormatArg = Literal["json", "markdown"]

FETCH_STRATEGIES = {"auto", "http_only", "scrapling_first", "browser_first", "browser_only"}
RETURN_FORMATS = {"json", "markdown"}

_pipeline: ReaderPipeline | None = None


def get_pipeline() -> ReaderPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ReaderPipeline.from_env()
    return _pipeline


def _build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise RuntimeError("mcp package is required to run the MCP server") from exc

    mcp = FastMCP("pyaireader")

    @mcp.tool()
    def reader_health() -> dict:
        """Return pyaireader MCP capabilities and local runtime defaults."""
        config = ReaderConfig.from_env()
        return {
            "success": True,
            "name": "pyaireader",
            "version": _package_version(),
            "transport": "stdio",
            "content_source": "untrusted_web",
            "tools": [
                "reader_health",
                "read_url_for_ai",
                "batch_read_urls_for_ai",
                "inspect_url",
                "clear_reader_cache",
            ],
            "fetch_strategies": sorted(FETCH_STRATEGIES),
            "cache_path": str(config.cache_path),
            "safety": {
                "public_http_https_only": True,
                "blocks_private_networks": True,
                "redirects_rechecked": True,
            },
        }

    @mcp.tool()
    def read_url_for_ai(
        url: str,
        fetch_strategy: FetchStrategyArg = "auto",
        bypass_cache: bool = False,
        ttl_seconds: int | None = None,
        max_total_chars: int = 16000,
        max_clean_text_chars: int = 12000,
        max_evidence_items: int = 12,
        max_number_mentions: int = 30,
        max_date_mentions: int = 30,
        max_entity_items: int = 40,
        return_format: ReturnFormatArg = "json",
    ) -> dict:
        """Read a public URL and return an AI-ready evidence pack with trace and quality data."""
        fetch_strategy = _validate_fetch_strategy(fetch_strategy)
        return_format = _validate_return_format(return_format)
        _validate_positive_int("max_total_chars", max_total_chars)
        _validate_positive_int("max_clean_text_chars", max_clean_text_chars)
        _validate_positive_int("max_evidence_items", max_evidence_items)
        _validate_positive_int("max_number_mentions", max_number_mentions)
        _validate_positive_int("max_date_mentions", max_date_mentions)
        _validate_positive_int("max_entity_items", max_entity_items)
        request = ReadUrlRequest(
            url=url,
            fetch_strategy=fetch_strategy,
            bypass_cache=bypass_cache,
            ttl_seconds=ttl_seconds,
            max_total_chars=max_total_chars,
            max_clean_text_chars=max_clean_text_chars,
            max_evidence_items=max_evidence_items,
            max_number_mentions=max_number_mentions,
            max_date_mentions=max_date_mentions,
            max_entity_items=max_entity_items,
            return_format=return_format,
        )
        return get_pipeline().read(request).to_dict()

    @mcp.tool()
    def batch_read_urls_for_ai(
        urls: list[str],
        fetch_strategy: FetchStrategyArg = "auto",
        bypass_cache: bool = False,
        max_concurrency: int = 3,
        max_total_chars_per_url: int = 16000,
        max_clean_text_chars_per_url: int = 12000,
    ) -> dict:
        """Read multiple public URLs and return one evidence result per URL."""
        fetch_strategy = _validate_fetch_strategy(fetch_strategy)
        if not urls:
            raise ValueError("urls must not be empty")
        _validate_positive_int("max_concurrency", max_concurrency)
        _validate_positive_int("max_total_chars_per_url", max_total_chars_per_url)
        _validate_positive_int("max_clean_text_chars_per_url", max_clean_text_chars_per_url)
        request = BatchReadUrlsRequest(
            urls=urls,
            fetch_strategy=fetch_strategy,
            bypass_cache=bypass_cache,
            max_concurrency=max_concurrency,
            max_total_chars_per_url=max_total_chars_per_url,
            max_clean_text_chars_per_url=max_clean_text_chars_per_url,
        )
        return get_pipeline().batch_read(request)

    @mcp.tool()
    def inspect_url(
        url: str,
        fetch_strategy: FetchStrategyArg = "auto",
        bypass_cache: bool = True,
        html_preview_chars: int = 2000,
    ) -> dict:
        """Inspect fetch/extract diagnostics for a public URL without returning full clean_text."""
        fetch_strategy = _validate_fetch_strategy(fetch_strategy)
        _validate_positive_int("html_preview_chars", html_preview_chars)
        return get_pipeline().inspect(
            InspectUrlRequest(
                url=url,
                fetch_strategy=fetch_strategy,
                bypass_cache=bypass_cache,
                html_preview_chars=html_preview_chars,
            )
        )

    @mcp.tool()
    def clear_reader_cache(url: str | None = None, domain: str | None = None) -> dict:
        """Clear pyaireader cache entries by exact URL, domain, or all entries."""
        return get_pipeline().clear_cache(url=url, domain=domain)

    return mcp


def main() -> None:
    server = _build_server()
    server.run(transport="stdio")


def _validate_fetch_strategy(value: str) -> FetchStrategyArg:
    if value not in FETCH_STRATEGIES:
        raise ValueError(f"fetch_strategy must be one of: {', '.join(sorted(FETCH_STRATEGIES))}")
    return value  # type: ignore[return-value]


def _validate_return_format(value: str) -> ReturnFormatArg:
    if value not in RETURN_FORMATS:
        raise ValueError(f"return_format must be one of: {', '.join(sorted(RETURN_FORMATS))}")
    return value  # type: ignore[return-value]


def _validate_positive_int(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")


def _package_version() -> str:
    try:
        return version("pyaireader")
    except PackageNotFoundError:
        return "0.1.0"


if __name__ == "__main__":
    main()
