from __future__ import annotations

import importlib.util
import os
import time
from datetime import datetime, timezone
from urllib.request import urlopen

from pyaireader.browser_sessions.base import (
    BrowserPageSnapshot,
    BrowserProviderStatus,
    BrowserReadOptions,
    BrowserSessionNotAvailable,
)
from pyaireader.reader.safety import assert_url_safe


class CDPBrowserSessionProvider:
    name = "cdp"

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or os.getenv("PYAIREADER_BROWSER_CDP")

    def is_available(self) -> bool:
        status = self.status()
        return status.available

    def open_page(self, url: str, options: BrowserReadOptions) -> BrowserPageSnapshot:
        if not self.is_available():
            raise BrowserSessionNotAvailable("cdp_browser_session_not_available")
        safe_url = assert_url_safe(url).url
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(self.endpoint)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
                page.goto(safe_url, wait_until="domcontentloaded", timeout=options.timeout_ms)
                _wait_for_page(page, options)
                snapshot = _snapshot(page, safe_url, self.name)
                page.close()
                return snapshot
        except Exception as exc:
            raise BrowserSessionNotAvailable(f"cdp_browser_session_failed: {exc}") from exc

    def status(self) -> BrowserProviderStatus:
        playwright_installed = importlib.util.find_spec("playwright") is not None
        endpoint = self.endpoint
        reachable = _endpoint_reachable(endpoint) if endpoint else False
        return BrowserProviderStatus(
            name=self.name,
            available=bool(endpoint and playwright_installed and reachable),
            details={
                "endpoint": endpoint,
                "playwright_installed": playwright_installed,
                "endpoint_reachable": reachable,
            },
        )


def _wait_for_page(page, options: BrowserReadOptions) -> None:  # noqa: ANN001
    if options.wait_for_selector:
        page.wait_for_selector(options.wait_for_selector, timeout=options.timeout_ms)
        return
    page.wait_for_selector("body", timeout=options.timeout_ms)
    if options.task_scope and options.task_scope.startswith("x_"):
        _wait_for_visible_text(page, min_length=500, timeout_ms=min(options.timeout_ms, 10_000))


def _wait_for_visible_text(page, *, min_length: int, timeout_ms: int) -> None:  # noqa: ANN001
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            text = page.locator("body").inner_text(timeout=500)
            if len(text or "") >= min_length:
                return
        except Exception:
            pass
        page.wait_for_timeout(250)


def _snapshot(page, url: str, provider: str) -> BrowserPageSnapshot:  # noqa: ANN001
    try:
        visible_text = page.locator("body").inner_text(timeout=1000)
    except Exception:
        visible_text = ""
    return BrowserPageSnapshot(
        url=url,
        final_url=page.url,
        title=page.title() or None,
        visible_text=visible_text,
        html=page.content(),
        captured_at=datetime.now(timezone.utc).isoformat(),
        provider=provider,
        user_session_used=True,
    )


def _endpoint_reachable(endpoint: str | None) -> bool:
    if not endpoint or not endpoint.startswith(("http://", "https://")):
        return False
    try:
        with urlopen(endpoint.rstrip("/") + "/json/version", timeout=1):
            return True
    except Exception:
        return False
