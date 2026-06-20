from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

import pyaireader.browser_sessions.edge_launcher as edge_launcher
import pyaireader.browser_sessions.fetcher as browser_session_fetcher
from pyaireader.browser_sessions import cdp_provider
from pyaireader.browser_sessions import BrowserSessionFetcher, launch_edge_cdp
from pyaireader.browser_sessions.base import BrowserReadOptions
from pyaireader.browser_sessions.cdp_provider import CDPBrowserSessionProvider


def test_browser_status_auto_without_cdp_does_not_open_persistent_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.delenv("PYAIREADER_BROWSER_PROVIDER", raising=False)
    monkeypatch.setattr(browser_session_fetcher, "discover_cdp_endpoint", lambda endpoint=None: None)

    status = BrowserSessionFetcher(profile_dir=tmp_path).status()

    assert status["provider_mode"] == "auto"
    assert status["cdp_endpoint"] is None
    assert status["profile_dir"] == str(tmp_path)
    assert status["active_provider"] is None
    assert status["available"] is False
    assert [provider["name"] for provider in status["providers"]] == ["cdp"]
    assert status["note"] == (
        "no_user_started_cdp_browser_available; start Edge/Chrome with remote debugging "
        "or explicitly choose persistent_profile"
    )


def test_browser_status_persistent_profile_requires_explicit_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.setattr(browser_session_fetcher, "discover_cdp_endpoint", lambda endpoint=None: None)

    status = BrowserSessionFetcher(provider_mode="persistent_profile", profile_dir=tmp_path).status()

    assert status["provider_mode"] == "persistent_profile"
    assert status["cdp_endpoint"] is None
    assert [provider["name"] for provider in status["providers"]] == ["persistent_profile"]
    assert status["note"] in {
        "using_pyaireader_persistent_profile",
        "no_browser_session_provider_available",
    }


def test_browser_status_auto_discovers_user_started_cdp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.delenv("PYAIREADER_BROWSER_PROVIDER", raising=False)
    monkeypatch.setattr(
        browser_session_fetcher,
        "discover_cdp_endpoint",
        lambda endpoint=None: "http://127.0.0.1:9333",
    )
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", lambda endpoint: True)

    status = BrowserSessionFetcher(provider_mode="auto").status()

    assert status["cdp_endpoint"] == "http://127.0.0.1:9333"
    assert status["active_provider"] == "cdp"
    assert [provider["name"] for provider in status["providers"]] == ["cdp"]
    assert status["note"] == "connected_to_user_started_cdp_browser"


def test_browser_status_forced_cdp_does_not_add_persistent_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.setattr(browser_session_fetcher, "discover_cdp_endpoint", lambda endpoint=None: None)

    status = BrowserSessionFetcher(provider_mode="cdp").status()

    assert status["provider_mode"] == "cdp"
    assert status["active_provider"] is None
    assert [provider["name"] for provider in status["providers"]] == ["cdp"]
    assert status["note"] == "cdp_requested_but_not_available"


def test_browser_status_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="browser provider must be one of"):
        BrowserSessionFetcher(provider_mode="edge")


def test_edge_cdp_launch_returns_structured_missing_executable(tmp_path: Path) -> None:
    result = launch_edge_cdp(edge_path=tmp_path / "missing-msedge.exe", wait_seconds=0)

    assert result["success"] is False
    assert result["message"] == "edge_executable_not_found"
    assert result["env"]["PYAIREADER_BROWSER_PROVIDER"] == "cdp"  # type: ignore[index]


def test_edge_cdp_launch_reports_reachable_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edge_path = tmp_path / "msedge.exe"
    edge_path.write_text("", encoding="utf-8")
    popen_calls = []

    class FakeProcess:
        pid = 1234

    def fake_popen(args, **kwargs):  # noqa: ANN001
        popen_calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(edge_launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(edge_launcher, "_wait_until_reachable", lambda port, wait_seconds: True)

    result = launch_edge_cdp(
        port=9333,
        edge_path=edge_path,
        user_data_dir=tmp_path / "edge-profile",
        wait_seconds=0,
    )

    assert result["success"] is True
    assert result["endpoint"] == "http://127.0.0.1:9333"
    assert result["process_id"] == 1234
    assert result["message"] == "edge_cdp_available"
    assert result["env"]["PYAIREADER_BROWSER_CDP"] == "http://127.0.0.1:9333"  # type: ignore[index]
    assert popen_calls
    assert "--remote-debugging-port=9333" in popen_calls[0][0]


def test_cdp_provider_reads_without_browser_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakeCDPPage()
    session = FakeCDPSession()

    class FakeContext:
        def __init__(self) -> None:
            self.new_page_called = False

        def expect_page(self) -> "FakeExpectPage":
            return FakeExpectPage(page)

        def new_page(self) -> FakeCDPPage:
            self.new_page_called = True
            return page

    class FakeBrowser:
        def __init__(self) -> None:
            self.context = FakeContext()
            self.contexts = [self.context]

        def new_browser_cdp_session(self) -> "FakeCDPSession":
            return session

    class FakeChromium:
        def connect_over_cdp(self, endpoint: str | None) -> FakeBrowser:
            assert endpoint == "http://127.0.0.1:9333"
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightManager:
        def __enter__(self) -> FakePlaywright:
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

    fake_sync_api = types.ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = lambda: FakePlaywrightManager()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)

    provider = CDPBrowserSessionProvider("http://127.0.0.1:9333")
    monkeypatch.setattr(provider, "is_available", lambda: True)

    snapshot = provider.open_page("https://example.com", options=BrowserReadOptions())

    assert snapshot.provider == "cdp"
    assert snapshot.visible_text == "Example Domain"
    assert page.closed is True
    assert session.sent == [
        (
            "Target.createTarget",
            {
                "url": "about:blank",
                "background": True,
            },
        )
    ]


def test_cdp_provider_can_disable_background_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakeCDPPage()

    class FakeContext:
        def new_page(self) -> FakeCDPPage:
            return page

    class FakeBrowser:
        contexts = [FakeContext()]

    class FakeChromium:
        def connect_over_cdp(self, endpoint: str | None) -> FakeBrowser:
            assert endpoint == "http://127.0.0.1:9333"
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

    class FakePlaywrightManager:
        def __enter__(self) -> FakePlaywright:
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

    fake_sync_api = types.ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = lambda: FakePlaywrightManager()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)

    provider = CDPBrowserSessionProvider("http://127.0.0.1:9333", background_pages=False)
    monkeypatch.setattr(provider, "is_available", lambda: True)

    snapshot = provider.open_page("https://example.com", options=BrowserReadOptions())

    assert snapshot.provider == "cdp"
    assert page.closed is True


class FakeCDPSession:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, object]]] = []

    def send(self, method: str, params: dict[str, object]) -> dict[str, object]:
        self.sent.append((method, params))
        return {"targetId": "target-1"}


class FakeExpectPage:
    def __init__(self, page: "FakeCDPPage") -> None:
        self.value = page

    def __enter__(self) -> "FakeExpectPage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


class FakeCDPPage:
    url = "https://example.com"

    def __init__(self) -> None:
        self.closed = False

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        assert url == "https://example.com"
        assert wait_until == "domcontentloaded"
        assert timeout == 30_000

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        assert selector == "body"
        assert timeout == 30_000

    def locator(self, selector: str) -> "FakeCDPLocator":
        assert selector == "body"
        return FakeCDPLocator()

    def title(self) -> str:
        return "Example Domain"

    def content(self) -> str:
        return "<html><body>Example Domain</body></html>"

    def close(self) -> None:
        self.closed = True


class FakeCDPLocator:
    def inner_text(self, *, timeout: int) -> str:
        assert timeout == 1000
        return "Example Domain"
