from __future__ import annotations

import importlib.util
import time
from typing import Literal

from pyaireader.errors import FetchError
from pyaireader.fetchers.http_fetcher import FetchResponse
from pyaireader.reader.safety import assert_url_safe


ScraplingMode = Literal["static", "dynamic", "stealth"]


class ScraplingFetcher:
    name = "scrapling"

    def __init__(self, mode: ScraplingMode = "static", timeout_ms: int = 20_000):
        self.mode = mode
        self.timeout_ms = timeout_ms

    def available(self) -> bool:
        return importlib.util.find_spec("scrapling") is not None

    def fetch(self, url: str) -> FetchResponse:
        if not self.available():
            raise FetchError("not_implemented: scrapling is not installed")

        start = time.perf_counter()
        safe_url = assert_url_safe(url).url
        try:
            response = self._fetch(safe_url)
        except Exception as exc:
            raise FetchError(f"scrapling fetch failed: {exc}") from exc

        final_url = str(getattr(response, "url", safe_url))
        assert_url_safe(final_url)
        raw = _response_body(response)
        text = _decode(raw, getattr(response, "encoding", "utf-8"))
        headers = dict(getattr(response, "headers", {}) or {})
        headers["x-pyaireader-engine"] = f"scrapling:{self.mode}"
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return FetchResponse(
            url=safe_url,
            final_url=final_url,
            status_code=int(getattr(response, "status", 0) or 0),
            content_type=headers.get("content-type", headers.get("Content-Type", "")),
            text=text,
            raw=raw,
            elapsed_ms=elapsed_ms,
            headers=headers,
        )

    def _fetch(self, url: str):
        if self.mode == "static":
            from scrapling import Fetcher

            return Fetcher.get(url)
        if self.mode == "dynamic":
            from scrapling import DynamicFetcher

            return DynamicFetcher.fetch(url, headless=True, wait=0, timeout=self.timeout_ms)
        if self.mode == "stealth":
            from scrapling import StealthyFetcher

            return StealthyFetcher.fetch(url, headless=True, wait=0, timeout=self.timeout_ms)
        raise FetchError(f"unknown scrapling mode: {self.mode}")


def _response_body(response) -> bytes:  # noqa: ANN001
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8", errors="ignore")
    html_content = getattr(response, "html_content", "")
    return str(html_content).encode("utf-8", errors="ignore")


def _decode(raw: bytes, encoding: str | None) -> str:
    return raw.decode(encoding or "utf-8", errors="replace")
