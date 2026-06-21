from __future__ import annotations

import importlib.util
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from pyaireader.browser_sessions.base import (
    BrowserPageSnapshot,
    BrowserProviderStatus,
    BrowserReadOptions,
    BrowserSessionNotAvailable,
)
from pyaireader.browser_sessions.edge_launcher import find_edge_executable
from pyaireader.browser_sessions.session_diagnostics import platform_session_status
from pyaireader.browser_runtime import run_sync_browser_operation
from pyaireader.reader.safety import assert_url_safe


class PersistentProfileBrowserSessionProvider:
    name = "persistent_profile"

    def __init__(
        self,
        profile_dir: Path,
        *,
        headless: bool = False,
        edge_path: str | Path | None = None,
        allow_chromium_fallback: bool | None = None,
    ) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self.edge_path = Path(edge_path) if edge_path else find_edge_executable()
        self.allow_chromium_fallback = (
            os.getenv("PYAIREADER_BROWSER_ALLOW_CHROMIUM_FALLBACK") == "1"
            if allow_chromium_fallback is None
            else allow_chromium_fallback
        )

    def is_available(self) -> bool:
        return self._playwright_installed() and self._browser_available()

    def status(self) -> BrowserProviderStatus:
        playwright_installed = self._playwright_installed()
        browser_available = self._browser_available()
        return BrowserProviderStatus(
            name=self.name,
            available=playwright_installed and browser_available,
            details={
                "browser": "edge",
                "profile_dir": str(self.profile_dir),
                "playwright_installed": playwright_installed,
                "edge_path": str(self.edge_path) if self.edge_path else None,
                "edge_available": self._edge_available(),
                "chromium_fallback_allowed": self.allow_chromium_fallback,
                "fallback_browser": "playwright_chromium"
                if self.allow_chromium_fallback and not self._edge_available()
                else None,
                "platform_sessions": platform_session_status(self.profile_dir),
                "headless": self.headless,
                "message": self._availability_error()
                if not playwright_installed or not browser_available
                else "edge_persistent_profile_available",
            },
        )

    def open_page(self, url: str, options: BrowserReadOptions) -> BrowserPageSnapshot:
        if not self.is_available():
            raise BrowserSessionNotAvailable(self._availability_error())
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
                    **self._launch_kwargs(headless=self.headless),
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
            raise BrowserSessionNotAvailable(self._availability_error())
        safe_url = assert_url_safe(url).url
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    **self._launch_kwargs(headless=False),
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

    def _playwright_installed(self) -> bool:
        return importlib.util.find_spec("playwright") is not None

    def _edge_available(self) -> bool:
        return self.edge_path is not None and self.edge_path.exists()

    def _browser_available(self) -> bool:
        return self._edge_available() or self.allow_chromium_fallback

    def _availability_error(self) -> str:
        if not self._playwright_installed():
            return "playwright_not_installed_for_persistent_profile"
        if not self._edge_available() and not self.allow_chromium_fallback:
            return "edge_executable_not_found_for_persistent_profile"
        return "persistent_profile_browser_session_not_available"

    def _launch_kwargs(self, *, headless: bool) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "user_data_dir": str(self.profile_dir),
            "headless": headless,
        }
        if self._edge_available():
            kwargs["executable_path"] = str(self.edge_path)
        return kwargs


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
