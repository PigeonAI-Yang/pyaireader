from __future__ import annotations

import importlib.util

from pyaireader.errors import FetchError
from pyaireader.fetchers.http_fetcher import FetchResponse, HttpFetcher


class PdfFetcher:
    name = "pdf"

    def __init__(self, http_fetcher: HttpFetcher | None = None):
        self.http_fetcher = http_fetcher or HttpFetcher()

    def available(self) -> bool:
        return importlib.util.find_spec("fitz") is not None

    def fetch(self, url: str) -> FetchResponse:
        if not self.available():
            raise FetchError("not_implemented: pymupdf is not installed")
        response = self.http_fetcher.fetch(url)
        response.headers["x-pyaireader-engine"] = self.name
        return response
