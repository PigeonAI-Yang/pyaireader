from __future__ import annotations

from pyaireader.extractors.text_extractor import extract_x_status
from pyaireader.platforms.base import PlatformContext
from pyaireader.platforms.x.article_reader import XArticleReader, extract_x_article_visible_text
from pyaireader.platforms.x.urls import (
    canonical_x_article_url,
    extract_only_url,
    find_x_article_url,
    is_tco_url,
    is_x_article_url,
    is_x_status_url,
)


class XStatusReader:
    name = "x_status"

    def __init__(self) -> None:
        self.article_reader = XArticleReader()

    def supports(self, url: str) -> bool:
        return is_x_status_url(url)

    def read(self, context: PlatformContext):
        if context.request.auth_strategy == "user_session_only":
            return self._read_with_user_session(context)

        response = context.fetch_url(context.normalized_url)
        extracted = extract_x_status(response.text, response.final_url)
        if not extracted:
            if context.request.auth_strategy == "user_session_fallback":
                return self._read_with_user_session(context)
            return None

        return self._build_status_result(context, response, extracted)

    def _build_status_result(self, context: PlatformContext, response, extracted):  # noqa: ANN001
        entry_url = extract_only_url(extracted.primary_text)
        if entry_url:
            article_url = find_x_article_url(response.text) or self._article_url_for_entry(
                context, entry_url
            )
            if article_url:
                context.trace.problem_flags.append("x_article_entry_detected")
                return self.article_reader.read_article(context, article_url)

        return context.build_success_result(response, extracted)

    def _read_with_user_session(self, context: PlatformContext):
        if context.fetch_user_session_url is None:
            return context.build_failure_result(
                context.normalized_url,
                "x_status_authenticated",
                "browser_session_not_available",
                ["browser_session_not_available"],
                "No local user-authorized browser session fetcher is available.",
                "configure_local_browser_session_or_use_anonymous",
            )
        try:
            response = context.fetch_user_session_url(context.normalized_url, "x_status")
        except Exception as exc:
            return context.build_failure_result(
                context.normalized_url,
                "x_status_authenticated",
                "browser_session_not_available",
                ["browser_session_not_available"],
                str(exc),
                "configure_local_browser_session_or_use_anonymous",
            )
        extracted = extract_x_article_visible_text(
            response.visible_text,
            response.final_url,
            page_title=response.headers.get("x-pyaireader-title"),
        )
        if extracted:
            return context.build_success_result(response, extracted)
        extracted = extract_x_status(response.text, response.final_url)
        if extracted:
            extracted.extractor = "x_status_authenticated"
            return self._build_status_result(context, response, extracted)
        code = (
            "user_session_login_required"
            if _looks_like_login_shell(response.text)
            else "browser_session_body_not_extracted"
        )
        return context.build_failure_result(
            response.final_url,
            "x_status_authenticated",
            code,
            [code],
            "The local user-authorized browser session did not expose a readable X status body.",
            "open_the_status_in_the_local_browser_session_or_provide_status_text",
        )

    def _article_url_for_entry(self, context: PlatformContext, entry_url: str) -> str | None:
        if is_x_article_url(entry_url):
            return canonical_x_article_url(entry_url)
        if not is_tco_url(entry_url):
            return None
        response = context.fetch_url(entry_url)
        if is_x_article_url(response.final_url):
            context.trace.problem_flags.append("x_article_url_expanded")
            return canonical_x_article_url(response.final_url)
        article_url = find_x_article_url(response.text)
        if article_url:
            context.trace.problem_flags.append("x_article_url_expanded")
            return article_url
        return None


def _looks_like_login_shell(text: str) -> bool:
    lowered = (text or "").lower()
    if "loggedoutshell" in lowered:
        return True
    markers = [
        "log in",
        "sign up",
        "create your account",
        "don’t miss what’s happening",
        "don't miss what's happening",
    ]
    return sum(1 for marker in markers if marker in lowered) >= 2
