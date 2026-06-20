from __future__ import annotations

import importlib.util
import time
from datetime import datetime, timezone
from pathlib import Path

from pyaireader.browser_sessions.base import (
    BrowserPageSnapshot,
    BrowserProviderStatus,
    BrowserReadOptions,
    BrowserSessionNotAvailable,
)
from pyaireader.browser_runtime import run_sync_browser_operation
from pyaireader.reader.safety import assert_url_safe


class PersistentProfileBrowserSessionProvider:
    name = "persistent_profile"

    def __init__(self, profile_dir: Path, *, headless: bool = False) -> None:
        self.profile_dir = profile_dir
        self.headless = headless

    def is_available(self) -> bool:
        return importlib.util.find_spec("playwright") is not None

    def status(self) -> BrowserProviderStatus:
        playwright_installed = importlib.util.find_spec("playwright") is not None
        return BrowserProviderStatus(
            name=self.name,
            available=playwright_installed,
            details={
                "profile_dir": str(self.profile_dir),
                "playwright_installed": playwright_installed,
                "headless": self.headless,
            },
        )

    def open_page(self, url: str, options: BrowserReadOptions) -> BrowserPageSnapshot:
        if not self.is_available():
            raise BrowserSessionNotAvailable("persistent_profile_browser_session_not_available")
        safe_url = assert_url_safe(url).url
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            return run_sync_browser_operation(lambda: self._open_page_sync(safe_url, options))
        except Exception as exc:
            raise BrowserSessionNotAvailable(
                f"persistent_profile_browser_session_failed: {exc}"
            ) from exc

    def _open_page_sync(self, safe_url: str, options: BrowserReadOptions) -> BrowserPageSnapshot:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=self.headless,
                )
                page = context.new_page()
                page.goto(safe_url, wait_until="domcontentloaded", timeout=options.timeout_ms)
                _wait_for_page(page, options)
                snapshot = _snapshot(page, safe_url, self.name)
                context.close()
                return snapshot
        except Exception as exc:
            raise BrowserSessionNotAvailable(str(exc)) from exc

    def open_interactive_login(self, url: str) -> None:
        if not self.is_available():
            raise BrowserSessionNotAvailable("persistent_profile_browser_session_not_available")
        safe_url = assert_url_safe(url).url
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=False,
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(safe_url, wait_until="domcontentloaded")
                try:
                    page.wait_for_event("close", timeout=0)
                finally:
                    context.close()
        except Exception as exc:
            raise BrowserSessionNotAvailable(
                f"persistent_profile_login_failed: {exc}"
            ) from exc


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
