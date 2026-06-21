from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import types

import pytest

import pyaireader.browser_sessions.edge_launcher as edge_launcher
import pyaireader.browser_sessions.fetcher as browser_session_fetcher
import pyaireader.browser_sessions.persistent_profile_provider as persistent_profile_provider
from pyaireader.browser_sessions import cdp_provider
from pyaireader.browser_sessions import (
    BrowserSessionFetcher,
    default_edge_cdp_profile_dir,
    launch_edge_cdp,
    launch_edge_cdp_profile,
)
from pyaireader.browser_sessions.base import BrowserReadOptions
from pyaireader.browser_sessions.cdp_provider import CDPBrowserSessionProvider
from pyaireader.browser_sessions.persistent_profile_provider import (
    PersistentProfileBrowserSessionProvider,
)


def test_browser_status_auto_without_cdp_does_not_open_persistent_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.delenv("PYAIREADER_BROWSER_PROVIDER", raising=False)
    monkeypatch.setattr(
        browser_session_fetcher,
        "discover_cdp_endpoint",
        lambda endpoint=None, dedicated_first=False: None,
    )
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", lambda endpoint: False)

    status = BrowserSessionFetcher(profile_dir=tmp_path).status()

    assert status["provider_mode"] == "auto"
    assert status["cdp_endpoint"] == "http://127.0.0.1:9334"
    assert status["profile_dir"] == str(tmp_path)
    assert status["active_provider"] is None
    assert status["available"] is False
    assert [provider["name"] for provider in status["providers"]] == ["edge_cdp_profile"]
    assert status["note"] == (
        "no_browser_cdp_available; run edge-cdp-profile-launch for logged-in sites "
        "or explicitly choose another provider"
    )


def test_browser_status_auto_does_not_use_generic_cdp_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PYAIREADER_BROWSER_CDP", "http://127.0.0.1:9333")
    monkeypatch.delenv("PYAIREADER_BROWSER_PROVIDER", raising=False)
    monkeypatch.delenv("PYAIREADER_EDGE_CDP_PROFILE_ENDPOINT", raising=False)
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", lambda endpoint: False)

    status = BrowserSessionFetcher(profile_dir=tmp_path).status()
    provider = status["providers"][0]  # type: ignore[index]

    assert status["provider_mode"] == "auto"
    assert status["active_provider"] is None
    assert status["cdp_endpoint"] == "http://127.0.0.1:9334"
    assert provider["details"]["endpoint"] == "http://127.0.0.1:9334"  # type: ignore[index]
    assert status["note"] == (
        "no_browser_cdp_available; run edge-cdp-profile-launch for logged-in sites "
        "or explicitly choose another provider"
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


def test_browser_status_auto_discovers_dedicated_edge_cdp_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.delenv("PYAIREADER_BROWSER_PROVIDER", raising=False)
    monkeypatch.setattr(
        browser_session_fetcher,
        "discover_cdp_endpoint",
        lambda endpoint=None, dedicated_first=False: "http://127.0.0.1:9334",
    )
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", lambda endpoint: True)

    status = BrowserSessionFetcher(provider_mode="auto").status()

    assert status["cdp_endpoint"] == "http://127.0.0.1:9334"
    assert status["active_provider"] == "edge_cdp_profile"
    assert [provider["name"] for provider in status["providers"]] == ["edge_cdp_profile"]
    assert status["note"] == "connected_to_dedicated_edge_cdp_profile"


def test_discover_cdp_endpoint_can_prefer_dedicated_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str | None] = []

    def fake_reachable(endpoint: str | None) -> bool:
        checked.append(endpoint)
        return endpoint == "http://127.0.0.1:9334"

    monkeypatch.setenv("PYAIREADER_BROWSER_CDP", "http://127.0.0.1:9333")
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", fake_reachable)

    endpoint = cdp_provider.discover_cdp_endpoint(dedicated_first=True)

    assert endpoint == "http://127.0.0.1:9334"
    assert checked == ["http://127.0.0.1:9334"]


def test_discover_cdp_endpoint_honors_explicit_cdp_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str | None] = []

    def fake_reachable(endpoint: str | None) -> bool:
        checked.append(endpoint)
        return endpoint == "http://127.0.0.1:9333"

    monkeypatch.setenv("PYAIREADER_BROWSER_CDP", "http://127.0.0.1:9333")
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", fake_reachable)

    endpoint = cdp_provider.discover_cdp_endpoint("http://127.0.0.1:9333")

    assert endpoint == "http://127.0.0.1:9333"
    assert checked[0] == "http://127.0.0.1:9333"


def test_browser_status_forced_cdp_does_not_add_persistent_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.setattr(
        browser_session_fetcher,
        "discover_cdp_endpoint",
        lambda endpoint=None, dedicated_first=False: None,
    )

    status = BrowserSessionFetcher(provider_mode="cdp").status()

    assert status["provider_mode"] == "cdp"
    assert status["active_provider"] is None
    assert [provider["name"] for provider in status["providers"]] == ["cdp"]
    assert status["note"] == "cdp_requested_but_not_available"


def test_browser_status_edge_cdp_profile_uses_dedicated_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PYAIREADER_BROWSER_CDP", "http://127.0.0.1:9333")
    monkeypatch.delenv("PYAIREADER_EDGE_CDP_PROFILE_ENDPOINT", raising=False)
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", lambda endpoint: False)

    status = BrowserSessionFetcher(
        provider_mode="edge_cdp_profile",
        profile_dir=tmp_path,
    ).status()

    assert status["provider_mode"] == "edge_cdp_profile"
    assert status["cdp_endpoint"] == "http://127.0.0.1:9334"
    assert status["profile_dir"] == str(tmp_path)
    assert [provider["name"] for provider in status["providers"]] == ["edge_cdp_profile"]
    assert status["note"] == "dedicated_edge_cdp_profile_not_available; run edge-cdp-profile-launch"


def test_browser_status_edge_cdp_profile_reports_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("PYAIREADER_BROWSER_CDP", raising=False)
    monkeypatch.setenv("PYAIREADER_EDGE_CDP_PROFILE_ENDPOINT", "http://127.0.0.1:9335")
    monkeypatch.setattr(cdp_provider, "_endpoint_reachable", lambda endpoint: endpoint.endswith(":9335"))
    monkeypatch.setattr(
        cdp_provider.importlib.util,
        "find_spec",
        lambda name: object() if name == "playwright" else None,
    )

    status = BrowserSessionFetcher(
        provider_mode="edge_cdp_profile",
        profile_dir=tmp_path,
    ).status()

    assert status["cdp_endpoint"] == "http://127.0.0.1:9335"
    assert status["active_provider"] == "edge_cdp_profile"
    assert status["note"] == "connected_to_dedicated_edge_cdp_profile"


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


def test_default_edge_cdp_profile_dir_uses_pyaireader_home() -> None:
    path = default_edge_cdp_profile_dir()

    assert path == Path.home() / ".pyaireader" / "edge-cdp-profiles" / "default"


def test_edge_cdp_profile_launch_returns_dedicated_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edge_path = tmp_path / "msedge.exe"
    edge_path.write_text("", encoding="utf-8")
    popen_calls = []

    class FakeProcess:
        pid = 4321

    def fake_popen(args, **kwargs):  # noqa: ANN001
        popen_calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(edge_launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(edge_launcher, "_wait_until_reachable", lambda port, wait_seconds: True)

    result = launch_edge_cdp_profile(
        profile="research",
        port=9334,
        edge_path=edge_path,
        profile_dir=tmp_path / "edge-profile",
        wait_seconds=0,
    )

    assert result["success"] is True
    assert result["provider"] == "edge_cdp_profile"
    assert result["endpoint"] == "http://127.0.0.1:9334"
    assert result["profile"] == "research"
    assert result["profile_dir"] == str(tmp_path / "edge-profile")
    assert result["non_disruptive"] is True
    assert result["message"] == "edge_cdp_profile_available"
    assert result["env"]["PYAIREADER_BROWSER_PROVIDER"] == "edge_cdp_profile"  # type: ignore[index]
    assert (  # type: ignore[index]
        result["env"]["PYAIREADER_EDGE_CDP_PROFILE_ENDPOINT"] == "http://127.0.0.1:9334"
    )
    assert f"--user-data-dir={tmp_path / 'edge-profile'}" in popen_calls[0][0]


def test_browser_login_edge_cdp_profile_launches_login_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    launch_calls: list[dict[str, object]] = []

    def fake_launch_edge_cdp_profile(**kwargs: object) -> dict[str, object]:
        launch_calls.append(kwargs)
        return {
            "success": True,
            "provider": "edge_cdp_profile",
            "endpoint": "http://127.0.0.1:9334",
        }

    monkeypatch.setattr(
        browser_session_fetcher,
        "launch_edge_cdp_profile",
        fake_launch_edge_cdp_profile,
    )

    result = BrowserSessionFetcher(
        provider_mode="edge_cdp_profile",
        profile_dir=tmp_path,
    ).open_login("x")

    assert result["success"] is True
    assert result["provider"] == "edge_cdp_profile"
    assert result["login_url"] == "https://x.com/home"
    assert launch_calls == [
        {
            "url": "https://x.com/home",
            "profile_dir": tmp_path,
            "port": 9334,
        }
    ]


def test_persistent_profile_status_reports_edge_browser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edge_path = tmp_path / "msedge.exe"
    edge_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(persistent_profile_provider, "find_edge_executable", lambda: edge_path)
    monkeypatch.setattr(
        persistent_profile_provider.importlib.util,
        "find_spec",
        lambda name: object() if name == "playwright" else None,
    )

    status = PersistentProfileBrowserSessionProvider(tmp_path / "profile").status()

    assert status.available is True
    assert status.details["browser"] == "edge"
    assert status.details["edge_path"] == str(edge_path)
    assert status.details["edge_available"] is True
    assert status.details["chromium_fallback_allowed"] is False
    assert status.details["message"] == "edge_persistent_profile_available"


def test_persistent_profile_status_reports_x_login_cookie_presence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edge_path = tmp_path / "msedge.exe"
    edge_path.write_text("", encoding="utf-8")
    cookie_db = tmp_path / "profile" / "Default" / "Network" / "Cookies"
    cookie_db.parent.mkdir(parents=True)
    connection = sqlite3.connect(cookie_db)
    try:
        connection.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
        connection.executemany(
            "INSERT INTO cookies (host_key, name) VALUES (?, ?)",
            [
                (".x.com", "auth_token"),
                (".x.com", "ct0"),
                (".x.com", "guest_id"),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    monkeypatch.setattr(persistent_profile_provider, "find_edge_executable", lambda: edge_path)
    monkeypatch.setattr(
        persistent_profile_provider.importlib.util,
        "find_spec",
        lambda name: object() if name == "playwright" else None,
    )

    status = PersistentProfileBrowserSessionProvider(tmp_path / "profile").status()
    x_status = status.details["platform_sessions"]["x"]  # type: ignore[index]

    assert x_status["logged_in"] is True
    assert x_status["present_auth_cookie_names"] == ["auth_token", "ct0"]
    assert x_status["message"] == "x_logged_in"


def test_persistent_profile_requires_edge_without_explicit_chromium_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(persistent_profile_provider, "find_edge_executable", lambda: None)
    monkeypatch.setattr(
        persistent_profile_provider.importlib.util,
        "find_spec",
        lambda name: object() if name == "playwright" else None,
    )

    provider = PersistentProfileBrowserSessionProvider(tmp_path / "profile")
    status = provider.status()

    assert provider.is_available() is False
    assert status.available is False
    assert status.details["edge_path"] is None
    assert status.details["message"] == "edge_executable_not_found_for_persistent_profile"


def test_persistent_profile_launches_edge_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    edge_path = tmp_path / "msedge.exe"
    edge_path.write_text("", encoding="utf-8")
    launch_calls: list[dict[str, object]] = []

    class FakePersistentContext:
        def new_page(self) -> FakeCDPPage:
            return FakeCDPPage()

        def close(self) -> None:
            return None

    class FakeChromium:
        def launch_persistent_context(self, **kwargs: object) -> FakePersistentContext:
            launch_calls.append(kwargs)
            return FakePersistentContext()

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

    provider = PersistentProfileBrowserSessionProvider(
        tmp_path / "profile",
        edge_path=edge_path,
    )
    monkeypatch.setattr(provider, "is_available", lambda: True)

    snapshot = provider.open_page("https://example.com", options=BrowserReadOptions())

    assert snapshot.provider == "persistent_profile"
    assert launch_calls
    assert launch_calls[0]["user_data_dir"] == str(tmp_path / "profile")
    assert launch_calls[0]["executable_path"] == str(edge_path)
    assert launch_calls[0]["headless"] is False


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
