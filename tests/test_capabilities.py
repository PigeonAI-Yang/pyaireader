from __future__ import annotations

from pyaireader.errors import FetchError
from pyaireader.fetchers import PdfFetcher, PlaywrightFetcher, ScraplingFetcher


def test_missing_optional_fetchers_fail_loudly() -> None:
    for fetcher in [ScraplingFetcher(), PlaywrightFetcher(), PdfFetcher()]:
        if fetcher.available():
            continue
        try:
            fetcher.fetch("https://example.com")
        except FetchError as exc:
            assert "not_implemented" in str(exc)
        else:
            raise AssertionError(f"{fetcher.name} returned success without dependency")
