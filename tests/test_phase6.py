from __future__ import annotations

import pytest

from pyaireader.errors import ExtractionError
from pyaireader.extractors import PdfExtractor
from pyaireader.fetchers import FetchResponse
from pyaireader.models import ReadUrlRequest
from pyaireader.config import ReaderConfig
from pyaireader.reader import ReaderPipeline
from pyaireader.versioning import ContentVersionStore
from pyaireader.watchers import extract_urls_from_rss, extract_urls_from_sitemap


def test_extract_urls_from_rss() -> None:
    xml = """
    <rss><channel>
      <item><link>https://example.com/a</link></item>
      <item><link>https://example.com/b</link></item>
    </channel></rss>
    """

    assert extract_urls_from_rss(xml) == ["https://example.com/a", "https://example.com/b"]


def test_extract_urls_from_sitemap() -> None:
    xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc></url>
    </urlset>
    """

    assert extract_urls_from_sitemap(xml) == ["https://example.com/a"]


def test_content_version_store_detects_change(tmp_path) -> None:
    store = ContentVersionStore(tmp_path / "versions.sqlite3")

    first = store.record("https://example.com/a", "sha256:first")
    second = store.record("https://example.com/a", "sha256:first")
    third = store.record("https://example.com/a", "sha256:second")

    assert first.changed is True
    assert second.changed is False
    assert third.changed is True


def test_pdf_extractor_missing_dependency_fails_loudly() -> None:
    extractor = PdfExtractor()
    if extractor.available():
        pytest.skip("pymupdf is installed; missing dependency behavior is not applicable")
    with pytest.raises(ExtractionError, match="not_implemented"):
        extractor.extract_bytes(b"%PDF")


def test_pipeline_extracts_pdf_from_fetch_response(tmp_path) -> None:
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "PDF evidence text 2026")
    pdf_bytes = document.tobytes()
    document.close()

    class PdfFakeFetcher:
        name = "fake_pdf"

        def fetch(self, url: str) -> FetchResponse:
            return FetchResponse(
                url=url,
                final_url=url,
                status_code=200,
                content_type="application/pdf",
                text="",
                raw=pdf_bytes,
                elapsed_ms=1,
            )

    pipeline = ReaderPipeline(config=ReaderConfig(cache_path=tmp_path / "cache.sqlite3"), fetcher=PdfFakeFetcher())
    result = pipeline.read(ReadUrlRequest(url="https://example.com/report.pdf", bypass_cache=True))

    assert result.success is True
    assert "PDF evidence text" in result.clean_text
    assert result.trace.extractor == "pdf"
