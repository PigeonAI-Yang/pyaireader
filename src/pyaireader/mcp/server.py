from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from pyaireader.config import ReaderConfig
from pyaireader.mcp.schemas import (
    BatchReadUrlsMcpResult,
    ClearCacheMcpResult,
    InspectUrlMcpResult,
    ReaderHealthMcpResult,
    ReadUrlMcpResult,
)
from pyaireader.models import (
    BATCH_READ_RESULT_SCHEMA_VERSION,
    HEALTH_SCHEMA_VERSION,
    INSPECT_RESULT_SCHEMA_VERSION,
    READ_RESULT_SCHEMA_VERSION,
    BatchReadUrlsRequest,
    InspectUrlRequest,
    ReadUrlRequest,
)
from pyaireader.reader import ReaderPipeline


FetchStrategyArg = Literal["auto", "http_only", "scrapling_first", "browser_first", "browser_only"]
ReturnFormatArg = Literal["json", "markdown"]
TransportLabel = Literal["stdio", "streamable-http"]

FETCH_STRATEGIES = {"auto", "http_only", "scrapling_first", "browser_first", "browser_only"}
RETURN_FORMATS = {"json", "markdown"}
STREAMABLE_HTTP_PATH = "/mcp"
MCP_TOOLS = [
    "reader_health",
    "read_url",
    "read_url_for_ai",
    "batch_read_urls",
    "batch_read_urls_for_ai",
    "inspect_url",
    "clear_reader_cache",
]

_pipeline: ReaderPipeline | None = None


def get_pipeline() -> ReaderPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ReaderPipeline.from_env()
    return _pipeline


def _build_server(
    *,
    transport_label: TransportLabel = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
):
    if transport_label == "streamable-http":
        _validate_loopback_http_host(host)
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.server import TransportSecuritySettings
        from mcp.types import ToolAnnotations
    except Exception as exc:
        raise RuntimeError("mcp package is required to run the MCP server") from exc

    health_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    read_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
    clear_cache_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    )
    security_settings = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_http_hosts(port),
        allowed_origins=_allowed_http_origins(port),
    )

    mcp = FastMCP(
        "pyaireader",
        host=host,
        port=port,
        streamable_http_path=STREAMABLE_HTTP_PATH,
        transport_security=security_settings,
    )

    @mcp.tool(annotations=health_annotations, structured_output=True)
    def reader_health() -> ReaderHealthMcpResult:
        """Return local reader capabilities, tool list, default parameters, cache path, and safety boundaries."""
        config = ReaderConfig.from_env()
        return ReaderHealthMcpResult.model_validate(
            {
                "schema_version": HEALTH_SCHEMA_VERSION,
                "success": True,
                "name": "pyaireader",
                "version": _package_version(),
                "transport": transport_label,
                "content_source": "untrusted_web",
                "tools": MCP_TOOLS,
                "schemas": {
                    "read_result": READ_RESULT_SCHEMA_VERSION,
                    "inspect_result": INSPECT_RESULT_SCHEMA_VERSION,
                    "batch_read_result": BATCH_READ_RESULT_SCHEMA_VERSION,
                    "health": HEALTH_SCHEMA_VERSION,
                },
                "fetch_strategies": sorted(FETCH_STRATEGIES),
                "return_formats": sorted(RETURN_FORMATS),
                "default_parameters": {
                    "fetch_strategy": "auto",
                    "bypass_cache": False,
                    "ttl_seconds": None,
                    "max_total_chars": config.max_total_chars,
                    "max_clean_text_chars": config.max_clean_text_chars,
                    "max_evidence_items": config.max_evidence_items,
                    "max_number_mentions": config.max_number_mentions,
                    "max_date_mentions": config.max_date_mentions,
                    "max_entity_items": config.max_entity_items,
                    "return_format": "json",
                    "batch_max_concurrency": 3,
                    "html_preview_chars": 2000,
                },
                "cache_path": str(config.cache_path),
                "safety": {
                    "public_http_https_only": True,
                    "blocks_private_networks": True,
                    "redirects_rechecked": True,
                    "blocks_userinfo_urls": True,
                    "blocks_metadata_ip": True,
                    "content_is_untrusted_evidence": True,
                },
                "mcp_http": {
                    "enabled": transport_label == "streamable-http",
                    "host": host if transport_label == "streamable-http" else None,
                    "port": port if transport_label == "streamable-http" else None,
                    "path": STREAMABLE_HTTP_PATH,
                    "loopback_only_by_default": True,
                    "allowed_origins": _allowed_http_origins(port),
                },
            }
        )

    @mcp.tool(annotations=read_annotations, structured_output=True)
    def read_url(
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
    ) -> ReadUrlMcpResult:
        """Read key content from a public URL for an AI Agent. Removes UI noise such as login buttons, navigation, ads, recommendation feeds, and footers. Returns clean_text, evidence, numbers, dates, entities, quality, and trace."""
        return _read_url_impl(
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

    @mcp.tool(annotations=read_annotations, structured_output=True)
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
    ) -> ReadUrlMcpResult:
        """Compatibility alias for read_url. Read key content from a public URL, remove UI noise, and return clean_text, evidence, quality, and trace for an AI Agent."""
        return _read_url_impl(
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

    @mcp.tool(annotations=read_annotations, structured_output=True)
    def batch_read_urls(
        urls: list[str],
        fetch_strategy: FetchStrategyArg = "auto",
        bypass_cache: bool = False,
        max_concurrency: int = 3,
        max_total_chars_per_url: int = 16000,
        max_clean_text_chars_per_url: int = 12000,
    ) -> BatchReadUrlsMcpResult:
        """Read key content from multiple public URLs for an AI Agent. Returns schema-stable clean_text, evidence, quality, and trace results for each URL."""
        return _batch_read_urls_impl(
            urls=urls,
            fetch_strategy=fetch_strategy,
            bypass_cache=bypass_cache,
            max_concurrency=max_concurrency,
            max_total_chars_per_url=max_total_chars_per_url,
            max_clean_text_chars_per_url=max_clean_text_chars_per_url,
        )

    @mcp.tool(annotations=read_annotations, structured_output=True)
    def batch_read_urls_for_ai(
        urls: list[str],
        fetch_strategy: FetchStrategyArg = "auto",
        bypass_cache: bool = False,
        max_concurrency: int = 3,
        max_total_chars_per_url: int = 16000,
        max_clean_text_chars_per_url: int = 12000,
    ) -> BatchReadUrlsMcpResult:
        """Compatibility alias for batch_read_urls. Read key content from multiple public URLs and return one result per URL."""
        return _batch_read_urls_impl(
            urls=urls,
            fetch_strategy=fetch_strategy,
            bypass_cache=bypass_cache,
            max_concurrency=max_concurrency,
            max_total_chars_per_url=max_total_chars_per_url,
            max_clean_text_chars_per_url=max_clean_text_chars_per_url,
        )

    @mcp.tool(annotations=read_annotations, structured_output=True)
    def inspect_url(
        url: str,
        fetch_strategy: FetchStrategyArg = "auto",
        bypass_cache: bool = True,
        html_preview_chars: int = 2000,
    ) -> InspectUrlMcpResult:
        """Diagnose why a public URL reads poorly. Returns fetch, extraction, quality, and trace diagnostics without returning the full clean_text."""
        fetch_strategy = _validate_fetch_strategy(fetch_strategy)
        _validate_positive_int("html_preview_chars", html_preview_chars)
        return InspectUrlMcpResult.model_validate(
            get_pipeline().inspect(
                InspectUrlRequest(
                    url=url,
                    fetch_strategy=fetch_strategy,
                    bypass_cache=bypass_cache,
                    html_preview_chars=html_preview_chars,
                )
            )
        )

    @mcp.tool(annotations=clear_cache_annotations, structured_output=True)
    def clear_reader_cache(url: str | None = None, domain: str | None = None) -> ClearCacheMcpResult:
        """Clear pyaireader cache entries by exact URL, domain, or all entries."""
        return ClearCacheMcpResult.model_validate(get_pipeline().clear_cache(url=url, domain=domain))

    return mcp


def _read_url_impl(
    *,
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
) -> ReadUrlMcpResult:
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
    return ReadUrlMcpResult.model_validate(get_pipeline().read(request).to_dict())


def _batch_read_urls_impl(
    *,
    urls: list[str],
    fetch_strategy: FetchStrategyArg = "auto",
    bypass_cache: bool = False,
    max_concurrency: int = 3,
    max_total_chars_per_url: int = 16000,
    max_clean_text_chars_per_url: int = 12000,
) -> BatchReadUrlsMcpResult:
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
    return BatchReadUrlsMcpResult.model_validate(get_pipeline().batch_read(request))


def main() -> None:
    server = _build_server(transport_label="stdio")
    server.run(transport="stdio")


def http_main() -> None:
    parser = argparse.ArgumentParser(description="Run pyaireader as an MCP Streamable HTTP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = _build_server(transport_label="streamable-http", host=args.host, port=args.port)
    server.run(transport="streamable-http")


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


def _validate_loopback_http_host(host: str) -> None:
    normalized = host.strip().strip("[]").lower()
    if normalized not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("pyaireader-mcp-http only supports loopback hosts by default")


def _allowed_http_hosts(port: int) -> list[str]:
    return [
        "127.0.0.1",
        f"127.0.0.1:{port}",
        "localhost",
        f"localhost:{port}",
        "::1",
        f"[::1]:{port}",
    ]


def _allowed_http_origins(port: int) -> list[str]:
    return [
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    ]


def _package_version() -> str:
    try:
        return version("pyaireader")
    except PackageNotFoundError:
        return "0.3.0"


if __name__ == "__main__":
    main()
