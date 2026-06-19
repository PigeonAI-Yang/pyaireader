from __future__ import annotations

from pathlib import Path

from pyaireader.cache import SQLiteReaderCache
from pyaireader.config import ReaderConfig
from pyaireader.fetchers import FetchResponse
from pyaireader.models import ReadUrlRequest
from pyaireader.reader import ReaderPipeline


HTML = """
<!doctype html>
<html>
  <head><title>测试公司公告</title></head>
  <body>
    <nav>导航噪声</nav>
    <article>
      <h1>测试公司公告</h1>
      <p>测试公司公告称，2026年6月19日，公司获得数据中心电力设备订单，金额为12.5亿元。</p>
      <p>公司预计上半年净利润同比增长45%至60%，主要受益于订单交付和产能释放。</p>
      <p>该项目涉及变压器、UPS和配电设备，交付周期预计持续到2027年。</p>
    </article>
  </body>
</html>
"""


class FakeFetcher:
    name = "fake_http"

    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, url: str) -> FetchResponse:
        self.calls += 1
        return FetchResponse(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html; charset=utf-8",
            text=HTML,
            raw=HTML.encode("utf-8"),
            elapsed_ms=1,
        )


def make_pipeline(tmp_path: Path, fetcher: FakeFetcher) -> ReaderPipeline:
    config = ReaderConfig(cache_path=tmp_path / "cache.sqlite3")
    return ReaderPipeline(config=config, fetcher=fetcher, cache=SQLiteReaderCache(config.cache_path))


def test_read_url_for_ai_returns_evidence(tmp_path: Path) -> None:
    fetcher = FakeFetcher()
    pipeline = make_pipeline(tmp_path, fetcher)

    result = pipeline.read(ReadUrlRequest(url="https://example.com/article"))

    assert result.success is True
    assert result.title == "测试公司公告"
    assert "12.5亿元" in result.clean_text
    assert result.evidence
    assert result.numbers
    assert result.dates
    assert result.entities
    assert result.financial_events
    assert result.summary is None
    assert result.key_points
    assert result.quality is not None
    assert result.trace.fetch_engine == "fake_http"
    assert result.trace.content_source == "untrusted_web"


def test_read_url_for_ai_uses_cache(tmp_path: Path) -> None:
    fetcher = FakeFetcher()
    pipeline = make_pipeline(tmp_path, fetcher)

    first = pipeline.read(ReadUrlRequest(url="https://example.com/article"))
    second = pipeline.read(ReadUrlRequest(url="https://example.com/article"))

    assert first.success is True
    assert second.success is True
    assert fetcher.calls == 1
    assert second.trace.cache_hit is True
    assert second.financial_events


def test_inspect_url_excludes_clean_text(tmp_path: Path) -> None:
    fetcher = FakeFetcher()
    pipeline = make_pipeline(tmp_path, fetcher)

    result = pipeline.inspect(ReadUrlRequest(url="https://example.com/article"))

    assert result["success"] is True
    assert result["trace"]["fetch_engine"] == "fake_http"
    assert "quality" in result
    assert "html_preview" in result
    assert "clean_text" not in result
