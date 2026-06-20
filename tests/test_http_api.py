from __future__ import annotations

from pyaireader.http.api import handle_api_request
from pyaireader.models import HEALTH_SCHEMA_VERSION


class FakePipeline:
    def read(self, request):
        return _Result({"success": True, "url": request.url})

    def batch_read(self, request):
        return {"success": True, "count": len(request.urls)}

    def inspect(self, request):
        return {"success": True, "url": request.url, "html_preview": ""}

    def search_platform(self, request):
        return _Result(
            {"success": True, "platform": request.platform, "query": request.query, "items": []}
        )

    def clear_cache(self, url=None, domain=None):
        return {"success": True, "url": url, "domain": domain}

    def storage_status(self):
        return {"success": True, "stores": [{"name": "default", "driver": "sqlite"}]}

    def library_list(self, **kwargs):
        return {
            "success": True,
            "store": kwargs.get("store", "default"),
            "count": 1,
            "items": [{"id": "ri_test", "clean_text_preview": "AI"}],
        }

    def library_get(self, item_id, store="default"):
        return {
            "success": True,
            "store": store,
            "item_id": item_id,
            "item": {"id": item_id, "clean_text": "full text"},
        }

    def library_search(self, query, **kwargs):
        return {
            "success": True,
            "store": kwargs.get("store", "default"),
            "query": query,
            "count": 1,
            "items": [{"id": "ri_test"}],
        }

    def save_reading_item(self, item, store="default"):
        return {
            "success": True,
            "store": store,
            "item_id": item["id"],
            "created": True,
            "item": item,
        }


class _Result:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


def test_handle_health() -> None:
    status, payload = handle_api_request("/health", {}, FakePipeline())

    assert status == 200
    assert payload["success"] is True
    assert payload["schema_version"] == HEALTH_SCHEMA_VERSION
    assert payload["auth_strategies"] == [
        "anonymous",
        "user_session_fallback",
        "user_session_only",
    ]
    assert payload["browser_session"]["provider_mode"] == "auto"


def test_handle_read_endpoint() -> None:
    status, payload = handle_api_request("/v1/read", {"url": "https://example.com"}, FakePipeline())

    assert status == 200
    assert payload == {"success": True, "url": "https://example.com"}


def test_handle_search_platform_endpoint() -> None:
    status, payload = handle_api_request(
        "/v1/search-platform",
        {"platform": "x", "query": "AAOI"},
        FakePipeline(),
    )

    assert status == 200
    assert payload == {"success": True, "platform": "x", "query": "AAOI", "items": []}


def test_handle_browser_status_endpoint() -> None:
    status, payload = handle_api_request("/v1/browser-status", {}, FakePipeline())

    assert status == 200
    assert payload["success"] is True
    assert payload["provider_mode"] == "auto"


def test_handle_storage_endpoints() -> None:
    pipeline = FakePipeline()

    status, payload = handle_api_request("/v1/storage-status", {}, pipeline)
    assert status == 200
    assert payload["success"] is True

    status, payload = handle_api_request("/v1/library/list", {}, pipeline)
    assert status == 200
    assert payload["items"][0]["id"] == "ri_test"

    status, payload = handle_api_request(
        "/v1/library/get",
        {"item_id": "ri_test"},
        pipeline,
    )
    assert status == 200
    assert payload["item"]["clean_text"] == "full text"

    status, payload = handle_api_request(
        "/v1/library/search",
        {"query": "AI"},
        pipeline,
    )
    assert status == 200
    assert payload["query"] == "AI"

    status, payload = handle_api_request(
        "/v1/library/save",
        {"store": "default", "item": {"id": "ri_test"}},
        pipeline,
    )
    assert status == 200
    assert payload["item_id"] == "ri_test"


def test_handle_unknown_endpoint() -> None:
    status, payload = handle_api_request("/missing", {}, FakePipeline())

    assert status == 404
    assert payload["success"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["suggested_next_action"] == "use_supported_endpoint"
