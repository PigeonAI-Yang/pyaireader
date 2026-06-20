from __future__ import annotations

import time
from dataclasses import dataclass, field
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pyaireader.errors import FetchError, UnsafeUrlError
from pyaireader.models import RedirectHop
from pyaireader.reader.safety import assert_url_safe


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    "Accept-Encoding": "identity",
}


@dataclass
class FetchResponse:
    url: str
    final_url: str
    status_code: int
    content_type: str
    text: str
    raw: bytes
    elapsed_ms: int
    visible_text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    redirects: list[RedirectHop] = field(default_factory=list)
    raw_bytes_length: int = 0
    html_length: int = 0
    text_length: int = 0

    def __post_init__(self) -> None:
        self.raw_bytes_length = self.raw_bytes_length or len(self.raw or b"")
        self.html_length = self.html_length or len(self.text or "")
        self.text_length = self.text_length or len(self.text or "")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class HttpFetcher:
    name = "http"

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        headers: dict[str, str] | None = None,
        max_redirects: int = 5,
    ):
        self.timeout_seconds = timeout_seconds
        self.headers = headers or DEFAULT_HEADERS
        self.max_redirects = max_redirects
        self._opener = build_opener(_NoRedirectHandler)

    def fetch(self, url: str) -> FetchResponse:
        start = time.perf_counter()
        current_url = assert_url_safe(url).url
        original_url = current_url
        redirects: list[RedirectHop] = []

        for _ in range(self.max_redirects + 1):
            try:
                response = self._open(current_url)
                raw = response.read()
                headers = _headers_to_dict(response.headers)
                content_type = response.headers.get("Content-Type", "")
                charset = response.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return FetchResponse(
                    url=original_url,
                    final_url=current_url,
                    status_code=getattr(response, "status", 200),
                    content_type=content_type,
                    text=text,
                    raw=raw,
                    elapsed_ms=elapsed_ms,
                    headers=headers,
                    redirects=redirects,
                )
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    location = exc.headers.get("Location")
                    if not location:
                        raise FetchError(f"HTTP redirect {exc.code} without Location") from exc
                    next_url = assert_url_safe(urljoin(current_url, location)).url
                    redirects.append(
                        RedirectHop(
                            from_url=current_url,
                            to_url=next_url,
                            status_code=exc.code,
                            safety_checked=True,
                        )
                    )
                    current_url = next_url
                    continue
                raise FetchError(f"HTTP {exc.code}: {exc.reason}") from exc
            except UnsafeUrlError:
                raise
            except URLError as exc:
                raise FetchError(str(exc.reason)) from exc
            except TimeoutError as exc:
                raise FetchError("fetch timeout") from exc

        raise FetchError(f"too many redirects, max={self.max_redirects}")

    def _open(self, url: str):
        request = Request(url, headers=self.headers, method="GET")
        return self._opener.open(request, timeout=self.timeout_seconds)


def _headers_to_dict(headers: Message) -> dict[str, str]:
    return {key: value for key, value in headers.items()}
