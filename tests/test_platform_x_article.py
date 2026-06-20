from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from pyaireader.cache import SQLiteReaderCache
from pyaireader.config import ReaderConfig
from pyaireader.fetchers import FetchResponse
from pyaireader.models import PlatformSearchRequest, ReadUrlRequest
from pyaireader.reader import ReaderPipeline


STATUS_WITH_ARTICLE_LINK_HTML = """
<!doctype html>
<html>
  <head>
    <title>Rahul on X: "https://t.co/0SEQLNWkBs" / X</title>
    <meta property="og:title" content="Rahul on X: &quot;https://t.co/0SEQLNWkBs&quot; / X">
  </head>
  <body>
    <main>
      <article>
        <div>Rahul</div>
        <div>@sairahul1</div>
        <time>9:29 · 2026年6月18日</time>
        <div>45.2万</div>
        <div>Views</div>
        <div>Read 20 replies</div>
      </article>
      <span>Log in</span>
      <span>Sign up</span>
    </main>
  </body>
</html>
"""

STATUS_WITH_NON_ARTICLE_LINK_HTML = """
<!doctype html>
<html>
  <head>
    <title>Rahul on X: "https://t.co/example123" / X</title>
    <meta property="og:title" content="Rahul on X: &quot;https://t.co/example123&quot; / X">
  </head>
  <body><main><article><div>@sairahul1</div></article></main></body>
</html>
"""

EMPTY_ARTICLE_HTML = """
<!doctype html>
<html>
  <head><title>X Article</title></head>
  <body>
    <script>
      window.__INITIAL_STATE__ = {
        "articleEntities": {"entities": {}},
        "publishedArticles": {"entities": {}}
      };
    </script>
    <div>LoggedOutShell</div>
  </body>
</html>
"""

ARTICLE_WITH_BODY_HTML = """
<!doctype html>
<html>
  <head><title>Readable X Article</title></head>
  <body>
    <script>
      window.__INITIAL_STATE__ = {
        "publishedArticles": {
          "entities": {
            "2067486749295816704": {
              "title": "Why local readers matter",
              "author": "Rahul",
              "publishedAt": "2026-06-18T09:29:00Z",
              "body": "AI agents need the actual article body, not the surrounding login chrome or a short redirect link. This article body is long enough to pass the platform extractor."
            }
          }
        }
      };
    </script>
  </body>
</html>
"""

JS_DISABLED_ARTICLE_HTML = """
<!doctype html>
<html>
  <head><title>JavaScript 不可用。</title></head>
  <body>
    <main>
      <span>We’ve detected that JavaScript is disabled in this browser.</span>
      <span>Please enable JavaScript or switch to a supported browser to continue using x.com.</span>
      <a>帮助中心</a>
      <span>服务条款 隐私政策 Cookie 政策 Imprint 广告信息 © 2026 X Corp.</span>
    </main>
  </body>
</html>
"""

X_SEARCH_HTML = """
<!doctype html>
<html>
  <body>
    <main>
      <article>
        <div>@analyst_one</div>
        <time>2h</time>
        <div>AAOI demand checks look stronger this week with visible optical order chatter.</div>
        <a href="/analyst_one/status/1001">Open</a>
      </article>
      <article>
        <div>@analyst_two</div>
        <time>3h</time>
        <div>AAOI options flow picked up after datacenter optics comments.</div>
        <a href="/analyst_two/status/1002">Open</a>
      </article>
    </main>
  </body>
</html>
"""

X_SEARCH_SIGNAL_HTML = """
<!doctype html>
<html>
  <body>
    <main>
      <article>
        <div>@echo_user</div>
        <time>1m</time>
        <div>Loop engineering https://t.co/example</div>
        <a href="/echo_user/status/2001">Open</a>
      </article>
      <article>
        <div>@method_user</div>
        <time>2m</time>
        <div>Prompt engineering was about what you say. Context engineering was about what you feed. Loop engineering is the system that runs the agent with gates, state, verifier checks, and budget limits.</div>
        <a href="/method_user/status/2002">Open</a>
      </article>
      <article>
        <div>@budget_user</div>
        <time>3m</time>
        <div>Loop engineering only works if token budget, automated tests, and stop conditions are designed before the automation runs.</div>
        <a href="/budget_user/status/2003">Open</a>
      </article>
    </main>
  </body>
</html>
"""

X_STATUS_DETAIL_HTML = """
<!doctype html>
<html>
  <head>
    <title>Analyst on X: "AAOI detailed note" / X</title>
    <meta property="og:title" content="Analyst on X: &quot;AAOI detailed note&quot; / X">
  </head>
  <body>
    <main>
      <article>
        <div>@analyst_one</div>
        <time>2h</time>
        <div>AAOI detailed note says transceiver demand and datacenter optics orders are improving.</div>
      </article>
    </main>
  </body>
</html>
"""

X_VISIBLE_ARTICLE_TEXT = """
要查看键盘快捷键，按下问号
主页
探索
通知
文章
查看新帖子
对话
Rahul
@sairahul1
订阅
6 AI Concepts You Must Master to Build Production-Ready AI Systems
20
72
324
46万
I watched a $200 bill appear on an AWS account overnight.
Not because the system crashed.
An agent ran in a loop for six hours with no stop condition, calling the OpenAI API on every iteration.
Every monitoring dashboard said it was healthy.
Nobody noticed until the invoice hit in the morning.
That is what happens when you build AI systems without understanding how they actually work.
Memory (RAG) + Thinking (LLM + Tokens) + Actions (Agents) + Measurement (Evals)
…assembled through Context Engineering.
The agent loops forever because nobody thought about stop conditions.
The RAG answers are wrong because nobody measured retrieval.
The prompt stops working over long sessions because nobody understood how the context window fills up.
If this was useful:
→ Repost to share it with every AI engineer you know
→ Follow @sairahul1 for more systems and breakdowns like this
下午5:29 · 2026年6月18日
·
46.7万
 查看
20
72
324
1,041
相关
查看引用
发布你的回复
回复
相关用户
"""


class MappingFetcher:
    name = "fake_http"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResponse:
        self.calls.append(url)
        parsed = urlparse(url)
        if parsed.hostname == "x.com" and "/sairahul1/status/" in parsed.path:
            return _response(url, url, STATUS_WITH_ARTICLE_LINK_HTML)
        if parsed.hostname == "x.com" and "/shell/status/" in parsed.path:
            return _response(url, url, "<html><body><div id='root'></div></body></html>")
        if parsed.hostname == "x.com" and "/nonarticle/status/" in parsed.path:
            return _response(url, url, STATUS_WITH_NON_ARTICLE_LINK_HTML)
        if parsed.hostname == "t.co" and parsed.path == "/0SEQLNWkBs":
            final_url = "https://x.com/i/article/2067486749295816704"
            return _response(url, final_url, EMPTY_ARTICLE_HTML)
        if parsed.hostname == "t.co" and parsed.path == "/example123":
            return _response(url, "https://example.com/readable-article", "<html>ok</html>")
        if parsed.hostname == "x.com" and parsed.path == "/i/article/2067486749295816704":
            return _response(url, url, EMPTY_ARTICLE_HTML)
        if parsed.hostname == "x.com" and parsed.path == "/i/article/111":
            return _response(url, url, ARTICLE_WITH_BODY_HTML)
        if parsed.hostname in {"publish.x.com", "cdn.syndication.twimg.com"}:
            return _response(url, url, "{}")
        raise AssertionError(f"unexpected fetch: {url}")


class FakeBrowserSessionFetcher:
    def __init__(self, mapping: dict[str, str | tuple[str, str]]) -> None:
        self.mapping = mapping
        self.calls: list[tuple[str, str | None]] = []

    def fetch(self, url: str, *, task_scope: str | None = None) -> FetchResponse:
        self.calls.append((url, task_scope))
        value = self.mapping.get(url)
        if value is None:
            parsed = urlparse(url)
            if parsed.hostname == "x.com" and "/search" in parsed.path:
                value = self.mapping.get("x_search")
            elif parsed.hostname == "x.com" and "/status/" in parsed.path:
                value = self.mapping.get("x_status_detail")
        if value is None:
            raise AssertionError(f"unexpected browser fetch: {url}")
        text, visible_text = value if isinstance(value, tuple) else (value, "")
        return _response(
            url,
            url,
            text,
            visible_text=visible_text,
            headers={
                "x-pyaireader-engine": "authenticated_browser",
                "x-pyaireader-browser-provider": "fake_browser",
            },
        )


def make_pipeline(
    tmp_path: Path,
    fetcher: MappingFetcher,
    browser_session_fetcher=None,
) -> ReaderPipeline:
    config = ReaderConfig(cache_path=tmp_path / "cache.sqlite3")
    return ReaderPipeline(
        config=config,
        fetcher=fetcher,
        browser_session_fetcher=browser_session_fetcher,
        cache=SQLiteReaderCache(config.cache_path),
    )


def test_x_status_short_link_to_article_fails_instead_of_short_link_success(
    tmp_path: Path,
) -> None:
    fetcher = MappingFetcher()
    pipeline = make_pipeline(tmp_path, fetcher)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://x.com/sairahul1/status/2067540315620405543?s=20",
            auth_strategy="anonymous",
            bypass_cache=True,
        )
    )

    assert result.success is False
    assert result.final_url == "https://x.com/i/article/2067486749295816704"
    assert result.clean_text == ""
    assert result.quality is not None
    assert result.quality.level == "failed"
    assert "x_article_body_not_extracted" in result.quality.flags
    assert "x_article_logged_out_shell" in result.quality.flags
    assert "x_article_public_endpoint_empty" in result.quality.flags
    assert result.error is not None
    error = result.error.to_dict() if hasattr(result.error, "to_dict") else result.error
    assert error["code"] == "x_article_body_not_extracted"
    assert error["suggested_next_action"] == "use_local_browser_session_or_provide_article_text"
    assert result.trace is not None
    assert "x_article_entry_detected" in result.trace.problem_flags
    assert "x_article_url_expanded" in result.trace.problem_flags


def test_x_status_short_link_to_non_article_keeps_status_behavior(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    pipeline = make_pipeline(tmp_path, fetcher)

    result = pipeline.read(
        ReadUrlRequest(url="https://x.com/nonarticle/status/1", bypass_cache=True)
    )

    assert result.success is True
    assert result.trace is not None
    assert result.trace.extractor == "x_status"
    assert result.final_url == "https://x.com/nonarticle/status/1"
    assert "https://t.co/example123" in result.clean_text


def test_x_article_extracts_body_from_published_articles_state(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    pipeline = make_pipeline(tmp_path, fetcher)

    result = pipeline.read(ReadUrlRequest(url="https://x.com/i/article/111", bypass_cache=True))

    assert result.success is True
    assert result.trace is not None
    assert result.trace.extractor == "x_article"
    assert result.title == "Why local readers matter"
    assert "AI agents need the actual article body" in result.clean_text
    assert result.author == "Rahul"
    assert result.published_at_raw == "2026-06-18T09:29:00Z"
    assert result.evidence
    assert result.evidence[0].reason == "x_article"


def test_x_article_empty_logged_out_state_returns_stable_failure(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    pipeline = make_pipeline(tmp_path, fetcher)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://x.com/i/article/2067486749295816704",
            auth_strategy="anonymous",
            bypass_cache=True,
        )
    )

    assert result.success is False
    assert result.final_url == "https://x.com/i/article/2067486749295816704"
    assert result.quality is not None
    assert result.quality.level == "failed"
    assert "x_article_body_not_extracted" in result.quality.flags
    assert result.error is not None
    error = result.error.to_dict() if hasattr(result.error, "to_dict") else result.error
    assert error["code"] == "x_article_body_not_extracted"


def test_x_article_user_session_fallback_extracts_authenticated_body(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher(
        {"https://x.com/i/article/2067486749295816704": ARTICLE_WITH_BODY_HTML}
    )
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://x.com/sairahul1/status/2067540315620405543?s=20",
            auth_strategy="user_session_fallback",
            bypass_cache=True,
        )
    )

    assert result.success is True
    assert result.final_url == "https://x.com/i/article/2067486749295816704"
    assert "AI agents need the actual article body" in result.clean_text
    assert result.trace is not None
    assert result.trace.extractor == "x_article_authenticated"
    assert result.trace.user_session_used is True
    assert result.trace.browser_provider == "fake_browser"
    assert result.trace.user_task_scope == "x_article"
    assert result.trace.visited_urls == ["https://x.com/i/article/2067486749295816704"]
    assert browser.calls == [("https://x.com/i/article/2067486749295816704", "x_article")]


def test_x_status_user_session_fallback_extracts_authenticated_status(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher({"x_status_detail": X_STATUS_DETAIL_HTML})
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://x.com/shell/status/1",
            auth_strategy="user_session_fallback",
            bypass_cache=True,
        )
    )

    assert result.success is True
    assert "AAOI detailed note" in result.clean_text
    assert result.trace is not None
    assert result.trace.extractor == "x_status_authenticated"
    assert result.trace.user_session_used is True
    assert result.trace.browser_provider == "fake_browser"
    assert result.trace.user_task_scope == "x_status"


def test_x_status_user_session_extracts_visible_article_text(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher(
        {"x_status_detail": ("<html><body><div id='react-root'></div></body></html>", X_VISIBLE_ARTICLE_TEXT)}
    )
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://x.com/shell/status/1",
            auth_strategy="user_session_only",
            bypass_cache=True,
        )
    )

    assert result.success is True
    assert "6 AI Concepts You Must Master" in result.clean_text
    assert "I watched a $200 bill appear" in result.clean_text
    assert "Context Engineering" in result.clean_text
    assert "相关用户" not in result.clean_text
    assert result.author == "Rahul (@sairahul1)"
    assert result.trace is not None
    assert result.trace.extractor == "x_article_authenticated"
    assert result.trace.user_session_used is True
    assert result.trace.browser_provider == "fake_browser"


def test_x_article_user_session_fallback_returns_login_required(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher(
        {"https://x.com/i/article/2067486749295816704": EMPTY_ARTICLE_HTML}
    )
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://x.com/i/article/2067486749295816704",
            auth_strategy="user_session_fallback",
            bypass_cache=True,
        )
    )

    assert result.success is False
    assert result.error is not None
    error = result.error.to_dict() if hasattr(result.error, "to_dict") else result.error
    assert error["code"] == "user_session_login_required"
    assert result.trace is not None
    assert result.trace.user_session_used is True
    assert result.trace.browser_provider == "fake_browser"


def test_x_article_user_session_fallback_rejects_js_disabled_shell(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher(
        {"https://x.com/i/article/2067486749295816704": JS_DISABLED_ARTICLE_HTML}
    )
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://x.com/i/article/2067486749295816704",
            auth_strategy="user_session_fallback",
            bypass_cache=True,
        )
    )

    assert result.success is False
    assert result.clean_text == ""
    assert result.error is not None
    error = result.error.to_dict() if hasattr(result.error, "to_dict") else result.error
    assert error["code"] == "browser_session_body_not_extracted"
    assert result.trace is not None
    assert result.trace.user_session_used is True
    assert result.trace.extractor == "x_article_authenticated"


def test_x_search_user_session_collects_bounded_results(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher(
        {
            "x_search": X_SEARCH_HTML,
            "x_status_detail": X_STATUS_DETAIL_HTML,
        }
    )
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.search_platform(
        PlatformSearchRequest(
            platform="x",
            query="AAOI",
            auth_strategy="user_session_fallback",
            max_results=1,
            max_pages=3,
            follow_links="same_platform",
        )
    )

    assert result.success is True
    assert len(result.items) == 1
    assert result.items[0].url == "https://x.com/analyst_one/status/1001"
    assert "AAOI detailed note" in result.items[0].text
    assert result.items[0].quality is not None
    assert result.items[0].quality.level != "failed"
    assert result.trace is not None
    assert result.trace.user_session_used is True
    assert result.trace.browser_provider == "fake_browser"
    assert result.trace.user_task_scope == "x_search:AAOI"
    assert result.visited_urls == result.trace.visited_urls
    assert len([call for call in browser.calls if call[1] == "x_search"]) == 1
    assert len([call for call in browser.calls if call[1] == "x_search_result"]) == 1


def test_x_search_short_results_are_usable_social_evidence(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher({"x_search": X_SEARCH_HTML})
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.search_platform(
        PlatformSearchRequest(
            platform="x",
            query="AAOI",
            auth_strategy="user_session_only",
            max_results=1,
            follow_links="none",
        )
    )

    assert result.success is True
    assert len(result.items) == 1
    assert result.items[0].quality is not None
    assert result.items[0].quality.level == "usable"
    assert result.items[0].evidence
    assert "AAOI demand checks" in result.items[0].text
    assert [call[1] for call in browser.calls] == ["x_search"]


def test_x_search_ranks_methodology_signals_over_echo_posts(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher({"x_search": X_SEARCH_SIGNAL_HTML})
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.search_platform(
        PlatformSearchRequest(
            platform="x",
            query="loop engineering",
            auth_strategy="user_session_only",
            max_results=2,
            follow_links="none",
        )
    )

    assert result.success is True
    assert len(result.items) == 2
    assert result.items[0].url == "https://x.com/method_user/status/2002"
    assert result.items[0].metrics["usefulness_score"] > result.items[1].metrics[
        "usefulness_score"
    ]
    assert "definition" in result.items[0].metrics["usefulness_signals"]
    assert "verifier" in result.items[0].metrics["usefulness_signals"]
    assert result.items[1].url == "https://x.com/budget_user/status/2003"
    assert all(item.url != "https://x.com/echo_user/status/2001" for item in result.items)


def test_x_search_anonymous_does_not_use_user_session(tmp_path: Path) -> None:
    fetcher = MappingFetcher()
    browser = FakeBrowserSessionFetcher({"x_search": X_SEARCH_HTML})
    pipeline = make_pipeline(tmp_path, fetcher, browser_session_fetcher=browser)

    result = pipeline.search_platform(
        PlatformSearchRequest(platform="x", query="AAOI", auth_strategy="anonymous")
    )

    assert result.success is False
    assert result.error is not None
    error = result.error.to_dict() if hasattr(result.error, "to_dict") else result.error
    assert error["code"] == "browser_session_required"
    assert result.trace is not None
    assert result.trace.user_session_used is False
    assert browser.calls == []


def _response(
    url: str,
    final_url: str,
    text: str,
    *,
    visible_text: str = "",
    headers: dict[str, str] | None = None,
) -> FetchResponse:
    return FetchResponse(
        url=url,
        final_url=final_url,
        status_code=200,
        content_type="text/html; charset=utf-8",
        text=text,
        raw=text.encode("utf-8"),
        elapsed_ms=1,
        visible_text=visible_text,
        headers=headers or {},
    )
