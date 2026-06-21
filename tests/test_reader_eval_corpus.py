from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest

from pyaireader.cache import SQLiteReaderCache
from pyaireader.config import ReaderConfig
from pyaireader.fetchers import FetchResponse
from pyaireader.models import PlatformSearchRequest, ReadUrlRequest
from pyaireader.reader import ReaderPipeline


NEWS_HTML = """
<!doctype html>
<html>
  <head><title>Grid demand rises as AI campuses expand</title></head>
  <body>
    <nav>Home Markets Login Subscribe</nav>
    <article>
      <h1>Grid demand rises as AI campuses expand</h1>
      <p>North American utilities are seeing faster interconnection requests from AI data
      center campuses, with transformer lead times stretching into 2027.</p>
      <p>The report says developers are reserving substations earlier and signing backup
      power contracts before land purchases close.</p>
      <p>Analysts expect switchgear, UPS systems, and medium-voltage equipment vendors to
      benefit as projects move from planning into procurement.</p>
      <p>The useful signal is power equipment demand, not the page navigation or account
      sign-in chrome around the story.</p>
      <p>Procurement teams said equipment availability has become a gating item for
      campus schedules, because transformers, breakers, and cooling power systems
      must be ordered long before servers are installed.</p>
      <p>Several utilities also asked developers to fund grid upgrades directly, which
      changes project economics and gives suppliers better backlog visibility.</p>
      <p>For investors, the relevant evidence is the shift from speculative site
      selection toward firm electrical equipment orders tied to named construction
      milestones.</p>
    </article>
    <aside>Trending stories</aside>
  </body>
</html>
"""

ANNOUNCEMENT_HTML = """
<!doctype html>
<html>
  <head><title>Example Power wins data center equipment order</title></head>
  <body>
    <header>Investor relations Search Contact</header>
    <main>
      <h1>Example Power wins data center equipment order</h1>
      <p>Example Power announced on June 21, 2026 that it received a $185 million
      order for transformers, switchgear, and power distribution cabinets.</p>
      <p>The customer is building a cloud computing campus in Texas, and shipments are
      expected to begin in the fourth quarter of 2026.</p>
      <p>Management said the project increases backlog visibility and supports factory
      utilization through 2027.</p>
    </main>
  </body>
</html>
"""

X_STATUS_HTML = """
<!doctype html>
<html>
  <head>
    <title>Researcher on X: "Loop engineering is not a prompt trick. It is the
    discipline of running agents with state, gates, tests, and stop conditions so
    work does not drift." / X</title>
    <meta property="og:title" content="Researcher on X: &quot;Loop engineering is
    not a prompt trick. It is the discipline of running agents with state, gates,
    tests, and stop conditions so work does not drift.&quot; / X">
  </head>
  <body>
    <main>
      <span>Log in</span><span>Sign up</span>
      <article>
        <div>Researcher</div>
        <div>@researcher</div>
        <div>Loop engineering is not a prompt trick. It is the discipline of running
        agents with state, gates, tests, and stop conditions so work does not drift.</div>
        <time>10:05 - Jun 21, 2026</time>
        <div>12K</div><div>Views</div>
      </article>
      <aside>Relevant people</aside>
    </main>
  </body>
</html>
"""

X_ARTICLE_HTML = """
<!doctype html>
<html>
  <head><title>Readable X Article</title></head>
  <body>
    <script>
      window.__INITIAL_STATE__ = {
        "publishedArticles": {
          "entities": {
            "123": {
              "title": "How to keep agent loops grounded",
              "author": "Researcher",
              "publishedAt": "2026-06-21T10:05:00Z",
              "body": "A useful agent loop needs a task source, a state file, a gate, and a report. The page shell, counters, and reply widgets are not the article body."
            }
          }
        }
      };
    </script>
  </body>
</html>
"""

X_SEARCH_HTML = """
<!doctype html>
<html>
  <body>
    <main>
      <article>
        <div>@echo</div>
        <time>1m</time>
        <div>Loop engineering https://t.co/short</div>
        <a href="/echo/status/1">Open</a>
      </article>
      <article>
        <div>@builder</div>
        <time>2m</time>
        <div>Loop engineering means building an agent workflow with state, verifier
        checks, tests, budget limits, and stop conditions before automation starts.</div>
        <a href="/builder/status/2">Open</a>
      </article>
    </main>
  </body>
</html>
"""

LOGIN_SHELL_HTML = """
<!doctype html>
<html><head><title>Sign in</title></head><body>Please sign in to continue.</body></html>
"""

JS_SHELL_HTML = """
<!doctype html>
<html><head><title>App</title></head><body><div id="root">Loading...</div></body></html>
"""


class EvalFetcher:
    name = "eval_http"

    def fetch(self, url: str) -> FetchResponse:
        parsed = urlparse(url)
        if parsed.path == "/news":
            return _response(url, NEWS_HTML)
        if parsed.path == "/announcement":
            return _response(url, ANNOUNCEMENT_HTML)
        if parsed.path == "/login-shell":
            return _response(url, LOGIN_SHELL_HTML)
        if parsed.path == "/js-shell":
            return _response(url, JS_SHELL_HTML)
        if parsed.hostname == "x.com" and "/status/123" in parsed.path:
            return _response(url, X_STATUS_HTML)
        if parsed.hostname == "x.com" and parsed.path == "/i/article/123":
            return _response(url, X_ARTICLE_HTML)
        raise AssertionError(f"unexpected eval fetch: {url}")


class EvalBrowserSessionFetcher:
    name = "authenticated_browser"

    def fetch(self, url: str, *, task_scope: str | None = None) -> FetchResponse:
        parsed = urlparse(url)
        if parsed.hostname == "x.com" and parsed.path == "/search":
            return _response(
                url,
                X_SEARCH_HTML,
                headers={
                    "x-pyaireader-engine": self.name,
                    "x-pyaireader-browser-provider": "eval_browser",
                    "x-pyaireader-task-scope": task_scope or "",
                },
            )
        raise AssertionError(f"unexpected eval browser fetch: {url}")


def test_reader_eval_corpus_positive_html_and_platform_cases(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path)

    cases = [
        ("https://example.com/news", "AI data\ncenter campuses", "Trending stories"),
        ("https://example.com/announcement", "$185 million", "Investor relations"),
        ("https://x.com/researcher/status/123", "Loop engineering is not", "Relevant people"),
        ("https://x.com/i/article/123", "A useful agent loop needs", "window.__INITIAL_STATE__"),
    ]

    for url, expected_text, forbidden_text in cases:
        result = pipeline.read(
            ReadUrlRequest(
                url=url,
                bypass_cache=True,
                fetch_strategy="http_only",
                auth_strategy="anonymous",
            )
        )

        assert result.success is True, url
        assert expected_text.replace("\n", " ") in result.clean_text.replace("\n", " ")
        assert forbidden_text not in result.clean_text
        assert result.final_url
        assert result.quality is not None
        assert result.quality.level != "failed"
        assert result.evidence
        assert result.trace is not None
        assert result.trace.content_source == "untrusted_web"


def test_reader_eval_corpus_pdf_path_when_dependency_available(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 520, 720),
        " ".join(["PDF corpus evidence text 2026 with audited reader content."] * 35),
    )
    pdf_bytes = document.tobytes()
    document.close()

    class PdfFetcher(EvalFetcher):
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

    pipeline = _pipeline(tmp_path, fetcher=PdfFetcher())
    result = pipeline.read(
        ReadUrlRequest(
            url="https://example.com/report.pdf",
            bypass_cache=True,
            fetch_strategy="http_only",
            auth_strategy="anonymous",
        )
    )

    assert result.success is True
    assert result.final_url == "https://example.com/report.pdf"
    assert "PDF corpus evidence text" in result.clean_text
    assert result.trace is not None
    assert result.trace.extractor == "pdf"
    assert result.quality is not None
    assert result.quality.level != "failed"
    assert result.evidence


def test_reader_eval_corpus_x_search_ranks_useful_result(tmp_path: Path) -> None:
    pipeline = _pipeline(tmp_path)

    result = pipeline.search_platform(
        PlatformSearchRequest(
            platform="x",
            query="loop engineering",
            auth_strategy="user_session_only",
            max_results=1,
            follow_links="none",
        )
    )

    assert result.success is True
    assert len(result.items) == 1
    item = result.items[0]
    assert item.url == "https://x.com/builder/status/2"
    assert "verifier checks" in item.text.replace("\n", " ")
    assert item.quality is not None
    assert item.quality.level != "failed"
    assert item.evidence
    assert item.metrics["usefulness_score"] > 0
    assert "link_only" not in item.metrics["usefulness_signals"]
    assert result.trace is not None
    assert result.trace.user_session_used is True
    assert result.trace.browser_provider == "eval_browser"


@pytest.mark.parametrize(
    ("url", "expected_flag"),
    [
        ("https://example.com/login-shell", "login_required"),
        ("https://example.com/js-shell", "js_shell"),
    ],
)
def test_reader_eval_corpus_rejects_shells_as_usable_content(
    tmp_path: Path,
    url: str,
    expected_flag: str,
) -> None:
    pipeline = _pipeline(tmp_path)

    result = pipeline.read(
        ReadUrlRequest(
            url=url,
            bypass_cache=True,
            fetch_strategy="http_only",
            auth_strategy="anonymous",
        )
    )

    assert result.quality is not None
    assert result.quality.level == "failed"
    assert expected_flag in result.quality.flags
    assert result.trace is not None
    assert expected_flag in result.trace.problem_flags


def _pipeline(tmp_path: Path, *, fetcher: EvalFetcher | None = None) -> ReaderPipeline:
    config = ReaderConfig(cache_path=tmp_path / "cache.sqlite3")
    return ReaderPipeline(
        config=config,
        fetcher=fetcher or EvalFetcher(),
        browser_session_fetcher=EvalBrowserSessionFetcher(),  # type: ignore[arg-type]
        cache=SQLiteReaderCache(config.cache_path),
    )


def _response(
    url: str,
    text: str,
    *,
    headers: dict[str, str] | None = None,
) -> FetchResponse:
    return FetchResponse(
        url=url,
        final_url=url,
        status_code=200,
        content_type="text/html; charset=utf-8",
        text=text,
        raw=text.encode("utf-8"),
        elapsed_ms=1,
        headers=headers or {},
    )
