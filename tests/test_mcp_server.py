from __future__ import annotations

import asyncio
import json

import pytest

from pyaireader.models import (
    BATCH_READ_RESULT_SCHEMA_VERSION,
    HEALTH_SCHEMA_VERSION,
    READ_RESULT_SCHEMA_VERSION,
)


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
        "read_url",
        "read_url_for_ai",
        "batch_read_urls",
        "batch_read_urls_for_ai",
        "browser_status",
        "search_platform",
        "collect_platform_evidence",
        "inspect_url",
        "clear_reader_cache",
        "storage_status",
        "save_reading_item",
        "library_list",
        "library_get",
        "library_search",
    }


def test_mcp_tools_expose_output_schema_and_annotations() -> None:
    from pyaireader.mcp.server import _build_server

    mcp = _build_server()
    tools = asyncio.run(mcp.list_tools())
    payloads = {tool.name: tool.model_dump(by_alias=True, exclude_none=True) for tool in tools}

    for name, payload in payloads.items():
        assert "outputSchema" in payload, name
        assert payload["outputSchema"]["type"] == "object"
        assert "success" in payload["outputSchema"]["properties"]
        assert "annotations" in payload, name

    assert payloads["read_url"]["outputSchema"] == payloads["read_url_for_ai"]["outputSchema"]
    assert payloads["batch_read_urls"]["outputSchema"] == payloads["batch_read_urls_for_ai"][
        "outputSchema"
    ]
    assert payloads["search_platform"]["outputSchema"] == payloads["collect_platform_evidence"][
        "outputSchema"
    ]
    assert payloads["reader_health"]["annotations"]["readOnlyHint"] is True
    assert payloads["reader_health"]["annotations"]["idempotentHint"] is True
    assert payloads["browser_status"]["annotations"]["readOnlyHint"] is True
    assert payloads["browser_status"]["annotations"]["idempotentHint"] is True
    assert payloads["browser_status"]["annotations"]["openWorldHint"] is False
    assert payloads["read_url"]["annotations"]["openWorldHint"] is True
    assert payloads["read_url"]["annotations"]["destructiveHint"] is False
    assert payloads["clear_reader_cache"]["annotations"]["readOnlyHint"] is False
    assert payloads["clear_reader_cache"]["annotations"]["destructiveHint"] is True
    assert payloads["storage_status"]["annotations"]["readOnlyHint"] is True
    assert payloads["save_reading_item"]["annotations"]["readOnlyHint"] is False
    assert payloads["save_reading_item"]["annotations"]["destructiveHint"] is False
    assert payloads["library_get"]["annotations"]["openWorldHint"] is False


def test_mcp_tool_descriptions_point_agents_to_reader_use_case() -> None:
    from pyaireader.mcp.server import _build_server

    mcp = _build_server()
    tools = asyncio.run(mcp.list_tools())
    descriptions = {tool.name: tool.description or "" for tool in tools}

    read_description = descriptions["read_url"]
    assert "key content" in read_description
    assert "UI noise" in read_description
    assert "clean_text" in read_description
    assert "quality" in read_description
    assert "trace" in read_description

    inspect_description = descriptions["inspect_url"]
    assert "Diagnose why" in inspect_description
    assert "without returning the full clean_text" in inspect_description

    health_description = descriptions["reader_health"]
    assert "tool list" in health_description
    assert "default parameters" in health_description
    assert "safety boundaries" in health_description


def test_reader_health_returns_schema_defaults_and_safety() -> None:
    from pyaireader.mcp.server import _build_server

    mcp = _build_server()
    payload = _call_tool_json(mcp, "reader_health", {})

    assert payload["schema_version"] == HEALTH_SCHEMA_VERSION
    assert "read_url" in payload["tools"]
    assert "read_url_for_ai" in payload["tools"]
    assert "batch_read_urls" in payload["tools"]
    assert "batch_read_urls_for_ai" in payload["tools"]
    assert "browser_status" in payload["tools"]
    assert "search_platform" in payload["tools"]
    assert "collect_platform_evidence" in payload["tools"]
    assert "storage_status" in payload["tools"]
    assert "library_get" in payload["tools"]
    assert payload["default_parameters"]["fetch_strategy"] == "auto"
    assert payload["default_parameters"]["auth_strategy"] == "user_session_fallback"
    assert payload["default_parameters"]["save"] is False
    assert payload["default_parameters"]["save_to"] == "default"
    assert payload["auth_strategies"] == [
        "anonymous",
        "user_session_fallback",
        "user_session_only",
    ]
    assert payload["schemas"]["read_result"] == READ_RESULT_SCHEMA_VERSION
    assert payload["schemas"]["reading_item"] == "pyaireader.reading_item.v1"
    assert payload["safety"]["public_http_https_only"] is True
    assert payload["safety"]["content_is_untrusted_evidence"] is True
    assert payload["browser_session"]["provider_mode"] == "auto"


def test_reader_health_reports_streamable_http_transport() -> None:
    from pyaireader.mcp.server import _build_server

    mcp = _build_server(transport_label="streamable-http", port=8123)
    payload = _call_tool_json(mcp, "reader_health", {})

    assert payload["transport"] == "streamable-http"
    assert payload["mcp_http"]["enabled"] is True
    assert payload["mcp_http"]["host"] == "127.0.0.1"
    assert payload["mcp_http"]["port"] == 8123
    assert payload["mcp_http"]["path"] == "/mcp"
    assert "http://127.0.0.1:8123" in payload["mcp_http"]["allowed_origins"]


def test_streamable_http_rejects_non_loopback_host() -> None:
    from pyaireader.mcp.server import _build_server

    with pytest.raises(ValueError, match="only supports loopback hosts"):
        _build_server(transport_label="streamable-http", host="0.0.0.0")


def test_read_url_aliases_share_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyaireader.mcp.server as server

    fake_pipeline = FakePipeline()
    monkeypatch.setattr(server, "get_pipeline", lambda: fake_pipeline)
    mcp = server._build_server()

    short = _call_tool_json(mcp, "read_url", {"url": "https://example.com"})
    long = _call_tool_json(mcp, "read_url_for_ai", {"url": "https://example.com"})

    assert short == long
    assert short["schema_version"] == READ_RESULT_SCHEMA_VERSION
    assert fake_pipeline.read_calls == 2


def test_read_url_returns_structured_content(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyaireader.mcp.server as server

    fake_pipeline = FakePipeline()
    monkeypatch.setattr(server, "get_pipeline", lambda: fake_pipeline)
    mcp = server._build_server()

    text_payload, structured_payload = _call_tool_payloads(
        mcp, "read_url", {"url": "https://example.com"}
    )

    assert structured_payload is not None
    assert structured_payload == text_payload
    assert structured_payload["schema_version"] == READ_RESULT_SCHEMA_VERSION
    assert structured_payload["success"] is True


def test_read_url_accepts_storage_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyaireader.mcp.server as server

    fake_pipeline = FakePipeline()
    monkeypatch.setattr(server, "get_pipeline", lambda: fake_pipeline)
    mcp = server._build_server()

    payload = _call_tool_json(
        mcp,
        "read_url",
        {
            "url": "https://example.com",
            "save": True,
            "save_to": "default",
            "project": "research",
            "tags": ["ai", "news"],
        },
    )

    assert payload["saved"] is True
    assert payload["saved_item_id"] == "ri_test"
    assert fake_pipeline.last_read_request.save is True
    assert fake_pipeline.last_read_request.project == "research"
    assert fake_pipeline.last_read_request.tags == ["ai", "news"]


def test_batch_read_url_aliases_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyaireader.mcp.server as server

    fake_pipeline = FakePipeline()
    monkeypatch.setattr(server, "get_pipeline", lambda: fake_pipeline)
    mcp = server._build_server()

    short = _call_tool_json(mcp, "batch_read_urls", {"urls": ["https://example.com"]})
    long = _call_tool_json(mcp, "batch_read_urls_for_ai", {"urls": ["https://example.com"]})

    assert short == long
    assert short["schema_version"] == BATCH_READ_RESULT_SCHEMA_VERSION
    assert fake_pipeline.batch_calls == 2


def test_platform_search_tools_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyaireader.mcp.server as server

    fake_pipeline = FakePipeline()
    monkeypatch.setattr(server, "get_pipeline", lambda: fake_pipeline)
    mcp = server._build_server()

    short = _call_tool_json(mcp, "search_platform", {"platform": "x", "query": "AAOI"})
    long = _call_tool_json(mcp, "collect_platform_evidence", {"platform": "x", "query": "AAOI"})

    assert short == long
    assert short["success"] is True
    assert short["platform"] == "x"
    assert short["query"] == "AAOI"
    assert fake_pipeline.search_calls == 2


def test_storage_tools_are_available(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyaireader.mcp.server as server

    fake_pipeline = FakePipeline()
    monkeypatch.setattr(server, "get_pipeline", lambda: fake_pipeline)
    mcp = server._build_server()

    status = _call_tool_json(mcp, "storage_status", {})
    listing = _call_tool_json(mcp, "library_list", {})
    item = _call_tool_json(mcp, "library_get", {"item_id": "ri_test"})
    search = _call_tool_json(mcp, "library_search", {"query": "AI"})

    assert status["success"] is True
    assert listing["items"][0]["id"] == "ri_test"
    assert item["item"]["clean_text"] == "full text"
    assert search["query"] == "AI"


def test_mcp_server_validates_fetch_strategy() -> None:
    from pyaireader.mcp.server import _validate_fetch_strategy

    assert _validate_fetch_strategy("auto") == "auto"
    with pytest.raises(ValueError, match="fetch_strategy must be one of"):
        _validate_fetch_strategy("browser_fast")


class FakePipeline:
    def __init__(self) -> None:
        self.read_calls = 0
        self.batch_calls = 0
        self.search_calls = 0
        self.last_read_request = None

    def read(self, request):
        self.read_calls += 1
        self.last_read_request = request
        return _Result(
            {
                "schema_version": READ_RESULT_SCHEMA_VERSION,
                "success": True,
                "url": request.url,
                "fetch_strategy": request.fetch_strategy,
                "saved": request.save,
                "saved_item_id": "ri_test" if request.save else None,
                "saved_to": request.save_to if request.save else None,
            }
        )

    def batch_read(self, request):
        self.batch_calls += 1
        return {
            "schema_version": BATCH_READ_RESULT_SCHEMA_VERSION,
            "success": True,
            "count": len(request.urls),
            "success_count": len(request.urls),
            "results": [],
        }

    def inspect(self, request):
        return {
            "success": True,
            "schema_version": "pyaireader.inspect_result.v1",
            "url": request.url,
            "html_preview": "",
        }

    def search_platform(self, request):
        self.search_calls += 1
        return _Result(
            {
                "success": True,
                "platform": request.platform,
                "query": request.query,
                "items": [],
                "visited_urls": [],
            }
        )

    def clear_cache(self, url=None, domain=None):
        return {"success": True, "deleted": 1, "url": url, "domain": domain}

    def storage_status(self):
        return {
            "success": True,
            "config_path": "stores.toml",
            "loaded_from_file": False,
            "default_store": "default",
            "stores": [],
            "reserved_drivers": [],
        }

    def save_reading_item(self, item, store="default"):
        return {"success": True, "store": store, "item_id": item["id"], "created": True, "item": item}

    def library_list(self, **kwargs):
        return {
            "success": True,
            "store": kwargs.get("store", "default"),
            "count": 1,
            "items": [_reading_item_summary()],
        }

    def library_get(self, item_id, store="default"):
        return {
            "success": True,
            "store": store,
            "item_id": item_id,
            "item": _reading_item(),
        }

    def library_search(self, query, **kwargs):
        return {
            "success": True,
            "store": kwargs.get("store", "default"),
            "query": query,
            "count": 1,
            "items": [_reading_item_summary()],
        }


class _Result:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


def _reading_item() -> dict:
    return {
        "id": "ri_test",
        "source_url": "https://example.com",
        "final_url": "https://example.com",
        "title": "AI",
        "author": None,
        "published_at_raw": None,
        "clean_text": "full text",
        "content_hash": "hash",
        "quality": {},
        "trace": {},
        "metadata": {},
        "tags": [],
        "project": None,
        "created_at": "2026-06-20T00:00:00+00:00",
        "schema_version": "pyaireader.reading_item.v1",
    }


def _reading_item_summary() -> dict:
    item = _reading_item()
    item.pop("clean_text")
    item["clean_text_length"] = 9
    item["clean_text_preview"] = "full text"
    return item


def _call_tool_json(mcp, name: str, arguments: dict) -> dict:
    payload, _structured = _call_tool_payloads(mcp, name, arguments)
    return payload


def _call_tool_payloads(mcp, name: str, arguments: dict) -> tuple[dict, dict | None]:
    result = asyncio.run(mcp.call_tool(name, arguments))
    if isinstance(result, tuple):
        content, structured = result
    else:
        content, structured = result, None
    assert len(content) == 1
    return json.loads(content[0].text), structured
