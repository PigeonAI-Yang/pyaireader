from __future__ import annotations

import os

import pytest

from pyaireader.fetchers import PlaywrightFetcher, ScraplingFetcher
from pyaireader.models import ReadUrlRequest
from pyaireader.reader import ReaderPipeline


RUN_NETWORK = os.getenv("PYAIREADER_RUN_NETWORK_TESTS") == "1"
RUN_BROWSER = os.getenv("PYAIREADER_RUN_BROWSER_TESTS") == "1"


@pytest.mark.network
@pytest.mark.skipif(not RUN_NETWORK, reason="set PYAIREADER_RUN_NETWORK_TESTS=1")
def test_scrapling_static_fetches_example_domain() -> None:
    fetcher = ScraplingFetcher()
    response = fetcher.fetch("https://example.com")

    assert response.status_code == 200
    assert "Example Domain" in response.text


@pytest.mark.browser
@pytest.mark.skipif(not (RUN_NETWORK and RUN_BROWSER), reason="set network and browser env flags")
@pytest.mark.parametrize("mode", ["dynamic", "stealth"])
def test_scrapling_browser_backed_modes_fetch_example_domain(mode: str) -> None:
    fetcher = ScraplingFetcher(mode=mode)  # type: ignore[arg-type]
    response = fetcher.fetch("https://example.com")

    assert response.status_code == 200
    assert "Example Domain" in response.text


@pytest.mark.browser
@pytest.mark.skipif(not (RUN_NETWORK and RUN_BROWSER), reason="set network and browser env flags")
def test_raw_browser_fetches_example_domain() -> None:
    fetcher = PlaywrightFetcher(timeout_ms=10_000)
    response = fetcher.fetch("https://example.com")

    assert response.status_code == 200
    assert "Example Domain" in response.text


@pytest.mark.network
@pytest.mark.skipif(not RUN_NETWORK, reason="set PYAIREADER_RUN_NETWORK_TESTS=1")
def test_pipeline_scrapling_first_returns_real_result() -> None:
    pipeline = ReaderPipeline()
    result = pipeline.read(
        ReadUrlRequest(
            url="https://example.com",
            fetch_strategy="scrapling_first",
            bypass_cache=True,
        )
    )

    assert result.success is True
    assert result.trace.fetch_engine == "scrapling:static"
    assert "Example Domain" in result.clean_text
