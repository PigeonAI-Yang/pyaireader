from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from contextlib import closing


def test_streamable_http_lists_tools_and_calls_health() -> None:
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "from pyaireader.mcp.server import _build_server; "
                f"_build_server(transport_label='streamable-http', port={port}).run("
                "transport='streamable-http')"
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_port(port, process)
        result = asyncio.run(_call_streamable_http(port))

        assert "reader_health" in result["tool_names"]
        assert "read_url" in result["tool_names"]
        assert "outputSchema" in result["read_url"]
        assert result["read_url"]["annotations"]["openWorldHint"] is True
        assert result["health"]["transport"] == "streamable-http"
        assert result["health"]["mcp_http"]["path"] == "/mcp"
    finally:
        _stop_process(process)


async def _call_streamable_http(port: int) -> dict:
    import httpx

    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    url = f"http://127.0.0.1:{port}/mcp"
    headers = {"Origin": f"http://127.0.0.1:{port}"}
    async with httpx.AsyncClient(headers=headers, timeout=10) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                health = await session.call_tool("reader_health", {})
                tool_payloads = {
                    tool.name: tool.model_dump(by_alias=True, exclude_none=True)
                    for tool in tools.tools
                }
                return {
                    "tool_names": [tool.name for tool in tools.tools],
                    "read_url": tool_payloads["read_url"],
                    "health": health.structuredContent,
                }


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, process: subprocess.Popen, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            _raise_process_failed(process)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    _raise_process_failed(process)


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _raise_process_failed(process: subprocess.Popen) -> None:
    stdout, stderr = process.communicate(timeout=1) if process.poll() is not None else ("", "")
    raise AssertionError(
        "streamable HTTP MCP server did not start\n"
        f"returncode={process.poll()}\nstdout={stdout}\nstderr={stderr}"
    )
