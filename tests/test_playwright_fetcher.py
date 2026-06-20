from __future__ import annotations

import asyncio
import sys
import threading
import types

from pyaireader.fetchers import PlaywrightFetcher


def test_raw_browser_fetcher_runs_sync_playwright_outside_running_loop(
    monkeypatch,
) -> None:
    called_from_threads: list[str] = []

    def fake_sync_playwright():
        called_from_threads.append(threading.current_thread().name)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:  # pragma: no cover - fails the test with a direct assertion message
            raise AssertionError("sync_playwright was called inside the active asyncio loop")
        return FakePlaywrightManager()

    fake_playwright_package = types.ModuleType("playwright")
    fake_playwright_package.__path__ = []  # type: ignore[attr-defined]
    fake_sync_api = types.ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = fake_sync_playwright  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", fake_playwright_package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    monkeypatch.setattr(PlaywrightFetcher, "available", lambda self: True)

    async def run_fetch():
        return PlaywrightFetcher(timeout_ms=1000).fetch("https://example.com")

    response = asyncio.run(run_fetch())

    assert response.status_code == 200
    assert response.final_url == "https://example.com"
    assert "Example Domain" in response.text
    assert response.headers["x-pyaireader-engine"] == "raw_browser"
    assert called_from_threads
    assert all(name.startswith("pyaireader-browser") for name in called_from_threads)


class FakePlaywrightManager:
    def __enter__(self):
        return FakePlaywright()

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


class FakePlaywright:
    chromium = None

    def __init__(self) -> None:
        self.chromium = FakeChromium()


class FakeChromium:
    def launch(self, *, headless: bool):
        assert headless is True
        return FakeBrowser()


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    def new_page(self):
        return FakePage()

    def close(self) -> None:
        self.closed = True


class FakePage:
    url = "https://example.com"

    def goto(self, url: str, *, wait_until: str, timeout: int):
        assert url == "https://example.com"
        assert wait_until == "domcontentloaded"
        assert timeout == 1000
        return FakeResponse()

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        assert state == "domcontentloaded"
        assert timeout == 1000

    def content(self) -> str:
        return "<html><head><title>Example Domain</title></head><body>Example Domain</body></html>"

    def title(self) -> str:
        return "Example Domain"


class FakeResponse:
    status = 200
    headers = {"content-type": "text/html; charset=utf-8"}
