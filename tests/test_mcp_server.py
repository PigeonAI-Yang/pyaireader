from __future__ import annotations

import asyncio

import pytest


def test_mcp_server_does_not_create_pipeline_at_import() -> None:
    import pyaireader.mcp.server as server

    assert server._pipeline is None


def test_mcp_server_registers_expected_tools() -> None:
    from pyaireader.mcp.server import _build_server

    mcp = _build_server()
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}

    assert names == {
        "reader_health",
        "read_url_for_ai",
        "batch_read_urls_for_ai",
        "inspect_url",
        "clear_reader_cache",
    }


def test_mcp_server_validates_fetch_strategy() -> None:
    from pyaireader.mcp.server import _validate_fetch_strategy

    assert _validate_fetch_strategy("auto") == "auto"
    with pytest.raises(ValueError, match="fetch_strategy must be one of"):
        _validate_fetch_strategy("browser_fast")
