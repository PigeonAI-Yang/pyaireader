from __future__ import annotations

from pathlib import Path

from pyaireader.cache import SQLiteReaderCache
from pyaireader.config import ReaderConfig
from pyaireader.fetchers import FetchResponse
from pyaireader.models import ReadUrlRequest
from pyaireader.reader import ReaderPipeline


X_STATUS_HTML = """
<!doctype html>
<html>
  <head>
    <title>Mat Velloso on X: "All day using GLM 5.2. Didn't miss much. First open model that passes the bar as a daily driver. Things are not going to be the same.
Damn, now I want to buy some serious hardware." / X</title>
    <meta property="og:title" content="Mat Velloso on X: &quot;All day using GLM 5.2. Didn't miss much. First open model that passes the bar as a daily driver. Things are not going to be the same.
Damn, now I want to buy some serious hardware.&quot; / X">
  </head>
  <body>
    <main>
      <span>Post</span>
      <span>Log in</span>
      <span>Sign up</span>
      <article>
        <div>Mat Velloso</div>
        <div>@matvelloso</div>
        <div>All day using GLM 5.2. Didn't miss much. First open model that passes the bar as a daily driver. Things are not going to be the same.</div>
        <div>Damn, now I want to buy some serious hardware.</div>
        <time>2:08 · 2026年6月19日</time>
        <div>1.6万</div>
        <div>Views</div>
        <div>Read 15 replies</div>
      </article>
      <aside>Relevant people</aside>
      <section>Trending now</section>
    </main>
  </body>
</html>
"""


class FakeXFetcher:
    name = "fake_http"

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html; charset=utf-8",
            text=X_STATUS_HTML,
            raw=X_STATUS_HTML.encode("utf-8"),
            elapsed_ms=1,
        )


def test_x_status_uses_structured_extraction(tmp_path: Path) -> None:
    config = ReaderConfig(cache_path=tmp_path / "cache.sqlite3")
    pipeline = ReaderPipeline(
        config=config,
        fetcher=FakeXFetcher(),
        cache=SQLiteReaderCache(config.cache_path),
    )

    result = pipeline.read(
        ReadUrlRequest(url="https://x.com/matvelloso/status/2067791546335019439?s=20")
    )

    assert result.success is True
    assert result.trace is not None
    assert result.trace.extractor == "x_status"
    assert result.source == "X"
    assert result.author == "Mat Velloso (@matvelloso)"
    assert result.published_at_raw == "2:08 · 2026年6月19日"
    assert result.quality is not None
    assert result.quality.level != "failed"
    assert "page_has_login_chrome" in result.quality.flags

    assert "All day using GLM 5.2" in result.clean_text
    assert "Damn, now I want to buy some serious hardware." in result.clean_text
    assert "Log in" not in result.clean_text
    assert "Sign up" not in result.clean_text
    assert "Trending" not in result.clean_text
    assert "Relevant people" not in result.clean_text

    assert result.evidence
    assert result.evidence[0].reason == "x_status"
    assert "All day using GLM 5.2" in result.evidence[0].text
    assert "Damn, now I want to buy some serious hardware." in result.evidence[0].text
