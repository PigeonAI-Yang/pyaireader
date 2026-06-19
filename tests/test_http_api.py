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

    def clear_cache(self, url=None, domain=None):
        return {"success": True, "url": url, "domain": domain}


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


def test_handle_read_endpoint() -> None:
    status, payload = handle_api_request("/v1/read", {"url": "https://example.com"}, FakePipeline())

    assert status == 200
    assert payload == {"success": True, "url": "https://example.com"}


def test_handle_unknown_endpoint() -> None:
    status, payload = handle_api_request("/missing", {}, FakePipeline())

    assert status == 404
    assert payload["success"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["suggested_next_action"] == "use_supported_endpoint"
