from __future__ import annotations

from email.message import Message
from io import BytesIO
from urllib.error import HTTPError

import pytest

from pyaireader.errors import UnsafeUrlError
from pyaireader.fetchers import HttpFetcher


def test_http_fetcher_rechecks_redirect_target_safety() -> None:
    fetcher = HttpFetcher()

    def fake_open(url: str):
        raise HTTPError(
            url=url,
            code=302,
            msg="Found",
            hdrs={"Location": "http://169.254.169.254/latest/meta-data/"},
            fp=BytesIO(),
        )

    fetcher._open = fake_open  # type: ignore[method-assign]

    with pytest.raises(UnsafeUrlError):
        fetcher.fetch("https://example.com/start")


def test_http_fetcher_records_manual_redirect_chain() -> None:
    fetcher = HttpFetcher()
    calls: list[str] = []

    def fake_open(url: str):
        calls.append(url)
        if len(calls) == 1:
            raise HTTPError(
                url=url,
                code=302,
                msg="Found",
                hdrs={"Location": "https://example.com/final"},
                fp=BytesIO(),
            )
        return _FakeResponse(url, b"<html>ok</html>")

    fetcher._open = fake_open  # type: ignore[method-assign]

    response = fetcher.fetch("https://example.com/start")

    assert response.status_code == 200
    assert response.final_url == "https://example.com/final"
    assert len(response.redirects) == 1
    assert response.redirects[0].safety_checked is True


class _FakeResponse:
    status = 200

    def __init__(self, url: str, body: bytes):
        self._url = url
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"

    def read(self) -> bytes:
        return self._body
