from __future__ import annotations

import importlib.util
import time

from pyaireader.browser_runtime import run_sync_browser_operation
from pyaireader.errors import FetchError
from pyaireader.fetchers.http_fetcher import FetchResponse
from pyaireader.reader.safety import assert_url_safe


class PlaywrightFetcher:
    name = "raw_browser"

    def __init__(self, timeout_ms: int = 30_000):
        self.timeout_ms = timeout_ms

    def available(self) -> bool:
        return importlib.util.find_spec("playwright") is not None

    def fetch(self, url: str) -> FetchResponse:
        if not self.available():
            raise FetchError("not_implemented: playwright is not installed")

        safe_url = assert_url_safe(url).url
        start = time.perf_counter()
        try:
            return run_sync_browser_operation(lambda: self._fetch_sync(safe_url, start))
        except Exception as exc:
            raise FetchError(f"raw browser fetch failed: {exc}") from exc

    def _fetch_sync(self, safe_url: str, start: float) -> FetchResponse:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                response = page.goto(safe_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                page.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
                final_url = page.url
                assert_url_safe(final_url)
                html = page.content()
                title = page.title()
                status_code = response.status if response else 0
                headers = response.headers if response else {}
                browser.close()
        except Exception as exc:
            raise FetchError(str(exc)) from exc

        raw = html.encode("utf-8", errors="ignore")
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        headers = dict(headers)
        headers["x-pyaireader-engine"] = "raw_browser"
        if title:
            headers["x-pyaireader-title"] = title
        return FetchResponse(
            url=safe_url,
            final_url=final_url,
            status_code=status_code,
            content_type=headers.get("content-type", headers.get("Content-Type", "text/html")),
            text=html,
            raw=raw,
            elapsed_ms=elapsed_ms,
            headers=headers,
        )
