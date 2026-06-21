from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin

from pyaireader.extractors.text_extractor import extract_x_status, normalize_text
from pyaireader.models import (
    PlatformSearchRequest,
    PlatformSearchResult,
    ReaderErrorPayload,
    ReaderTrace,
)
from pyaireader.platforms.x.evidence_collector import build_platform_evidence_item


class XSearchReader:
    name = "x_search"

    def search(
        self,
        request: PlatformSearchRequest,
        trace: ReaderTrace,
        fetch_user_session_url,
        fetch_anonymous_url,
    ) -> PlatformSearchResult:
        trace.user_task_scope = f"x_search:{request.query.strip()}"
        if request.platform != "x":
            return _failure(request, trace, "unsupported_platform", "Only platform='x' is supported.")
        if not request.query.strip():
            return _failure(request, trace, "invalid_request", "query must not be empty.")
        if request.auth_strategy == "anonymous":
            return _failure(
                request,
                trace,
                "browser_session_required",
                "X platform search requires a local user-authorized browser session.",
            )

        candidates: list[_SearchCandidate] = []
        for search_url in _bounded_search_urls(request):
            try:
                response = fetch_user_session_url(search_url, "x_search")
            except Exception as exc:
                return _failure(request, trace, "browser_session_not_available", str(exc))
            trace.visited_urls = _dedupe([*trace.visited_urls, response.final_url])
            if _looks_like_x_login_page(response):
                return _failure(
                    request,
                    trace,
                    "x_login_required",
                    "X search opened a login page. Log in to the pyaireader browser profile and retry.",
                )
            candidates.extend(_extract_search_candidates(response.text, base_url=response.final_url))
            if len(candidates) >= request.max_results:
                break
        candidates = _rank_candidates(request.query, _dedupe_candidates(candidates))
        if not candidates:
            return _failure(request, trace, "platform_search_no_results", "No X search results found.")

        items = []
        for candidate in candidates[: request.max_results]:
            text = candidate.text
            author = candidate.author
            published_at_raw = candidate.published_at_raw
            if request.follow_links != "none":
                try:
                    detail = fetch_user_session_url(candidate.url, "x_search_result")
                    trace.visited_urls = _dedupe([*trace.visited_urls, detail.final_url])
                    extracted = extract_x_status(detail.text, detail.final_url)
                    if extracted and extracted.clean_text:
                        text = extracted.clean_text
                        author = extracted.author
                        published_at_raw = extracted.published_at_raw
                except Exception:
                    pass
            relevance = _relevance(request.query, text)
            usefulness_score, usefulness_signals = _usefulness(request.query, text)
            items.append(
                build_platform_evidence_item(
                    url=candidate.url,
                    text=text,
                    author=author,
                    published_at_raw=published_at_raw,
                    relevance=relevance,
                    metrics={
                        "usefulness_score": usefulness_score,
                        "usefulness_signals": usefulness_signals,
                    },
                )
            )

        return PlatformSearchResult(
            success=True,
            platform=request.platform,
            query=request.query,
            items=items,
            trace=trace,
            error=None,
            visited_urls=trace.visited_urls,
        )


class _SearchCandidate:
    def __init__(
        self,
        *,
        url: str,
        text: str,
        author: str | None = None,
        published_at_raw: str | None = None,
    ) -> None:
        self.url = url
        self.text = text
        self.author = author
        self.published_at_raw = published_at_raw


class _SearchHTMLParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.candidates: list[_SearchCandidate] = []
        self._skip_depth = 0
        self._article_depth = 0
        self._article_text: list[str] = []
        self._article_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "article":
            self._article_depth += 1
            self._article_text = []
            self._article_links = []
        if self._article_depth and tag == "a":
            href = attr_map.get("href")
            if href and re.search(r"/status/\d+", href):
                self._article_links.append(urljoin(self.base_url, href))
        if self._article_depth and tag in {"p", "div", "span", "time"}:
            self._article_text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "article" and self._article_depth:
            self._article_depth -= 1
            if self._article_depth == 0:
                self._flush_article()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not self._article_depth:
            return
        if data.strip():
            self._article_text.append(data)

    def _flush_article(self) -> None:
        if not self._article_links:
            return
        text = normalize_text("\n".join(self._article_text))
        if len(text) < 20:
            return
        self.candidates.append(
            _SearchCandidate(
                url=self._article_links[0],
                text=text,
                author=_extract_author(text),
                published_at_raw=_extract_published(text),
            )
        )


def _x_search_url(query: str, time_range: str) -> str:
    query_text = query.strip()
    if time_range == "24h":
        query_text = f"{query_text} filter:links OR {query_text}"
    return f"https://x.com/search?q={quote_plus(query_text)}&src=typed_query&f=live"


def _bounded_search_urls(request: PlatformSearchRequest) -> list[str]:
    # X does not expose stable numbered search pages in the web UI. Phase 1 reads one bounded
    # rendered results page and then opens at most max_results result URLs.
    page_count = min(request.max_pages, 1)
    return [_x_search_url(request.query, request.time_range) for _ in range(page_count)]


def _extract_search_candidates(document: str, *, base_url: str) -> list[_SearchCandidate]:
    parser = _SearchHTMLParser(base_url)
    parser.feed(document)
    return _dedupe_candidates(parser.candidates)


def _looks_like_x_login_page(response) -> bool:  # noqa: ANN001
    final_url = (getattr(response, "final_url", "") or "").lower()
    if "/i/jf/onboarding/" in final_url:
        return True
    if "mode=login" in final_url or "redirect_after_login=" in final_url:
        return True
    visible_text = normalize_text(getattr(response, "visible_text", "") or "").lower()
    if "log in" in visible_text and "sign up" in visible_text:
        return True
    return False


def _rank_candidates(query: str, candidates: list[_SearchCandidate]) -> list[_SearchCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: _usefulness(query, candidate.text)[0],
        reverse=True,
    )


def _extract_author(text: str) -> str | None:
    match = re.search(r"@([A-Za-z0-9_]{1,15})\b", text)
    return f"@{match.group(1)}" if match else None


def _extract_published(text: str) -> str | None:
    for line in text.splitlines():
        if re.search(r"\b\d{4}年\d{1,2}月\d{1,2}日\b", line):
            return line
        if re.search(r"\b\d{1,2}[hm]\b", line):
            return line
    return None


def _relevance(query: str, text: str) -> float:
    terms = [term.lower() for term in re.findall(r"[A-Za-z0-9$._-]+", query)]
    lowered = text.lower()
    if not terms:
        return 0.0
    hits = sum(1 for term in terms if term in lowered)
    return round(hits / len(terms), 3)


def _usefulness(query: str, text: str) -> tuple[float, list[str]]:
    lowered = text.lower()
    relevance = _relevance(query, text)
    signals: list[str] = []
    score = relevance * 0.35
    text_length = len(text.strip())

    if text_length >= 280:
        score += 0.18
        signals.append("substantive_length")
    elif text_length >= 120:
        score += 0.1
        signals.append("some_context")
    elif text_length < 80:
        score -= 0.18
        signals.append("very_short")

    signal_groups = {
        "definition": r"\b(is|means|refers to|about|definition|defined)\b|下一|是指",
        "methodology": r"\b(method|roadmap|framework|checklist|steps?|patterns?|system)\b",
        "implementation": r"\b(build|implement|run|state file|automation|workflow|agent)\b",
        "verifier": r"\b(verifier|verify|test|lint|gate|check|eval)\b",
        "budget": r"\b(token|cost|budget|affordable|pricing|spend)\b",
        "critique": r"\b(why|risk|problem|hype|instead of|concern|tradeoff)\b",
        "article": r"\b(article|longform|read|thread)\b|文章",
    }
    weights = {
        "definition": 0.14,
        "methodology": 0.14,
        "implementation": 0.12,
        "verifier": 0.12,
        "budget": 0.1,
        "critique": 0.08,
        "article": 0.08,
    }
    for name, pattern in signal_groups.items():
        if re.search(pattern, lowered):
            score += weights[name]
            signals.append(name)

    if _looks_link_only(text):
        score -= 0.22
        signals.append("link_only")
    if _looks_echo_only(query, text):
        score -= 0.24
        signals.append("echo_only")

    return round(max(0.0, min(score, 1.0)), 3), signals


def _looks_link_only(text: str) -> bool:
    words = re.findall(r"[A-Za-z0-9_]+", text)
    return "http" in text.lower() and len(words) <= 8


def _looks_echo_only(query: str, text: str) -> bool:
    normalized_query = " ".join(re.findall(r"[A-Za-z0-9]+", query.lower()))
    normalized_text = " ".join(re.findall(r"[A-Za-z0-9]+", text.lower()))
    if not normalized_query or normalized_query not in normalized_text:
        return False
    extra = normalized_text.replace(normalized_query, " ").strip()
    return len(extra.split()) <= 5


def _failure(
    request: PlatformSearchRequest,
    trace: ReaderTrace,
    code: str,
    message: str,
) -> PlatformSearchResult:
    trace.problem_flags = _dedupe([*trace.problem_flags, code])
    return PlatformSearchResult(
        success=False,
        platform=request.platform,
        query=request.query,
        items=[],
        trace=trace,
        error=ReaderErrorPayload(
            code=code,
            message=message,
            retryable=code in {"browser_session_not_available", "x_login_required"},
            suggested_next_action="use_local_browser_session_or_reduce_scope",
            type="PlatformSearchError",
        ),
        visited_urls=trace.visited_urls,
    )


def _dedupe_candidates(candidates: list[_SearchCandidate]) -> list[_SearchCandidate]:
    output: list[_SearchCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.url not in seen:
            output.append(candidate)
            seen.add(candidate.url)
    return output


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            output.append(item)
            seen.add(item)
    return output
