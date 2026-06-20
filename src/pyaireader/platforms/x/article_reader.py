from __future__ import annotations

import json
import re
from typing import Any

from pyaireader.extractors import ExtractedText, TextExtractor
from pyaireader.extractors.text_extractor import normalize_text
from pyaireader.fetchers import FetchResponse
from pyaireader.platforms.base import PlatformContext
from pyaireader.platforms.x.urls import (
    canonical_x_article_url,
    extract_x_article_id,
    is_x_article_url,
    x_oembed_url,
    x_syndication_url,
)


class XArticleReader:
    name = "x_article"

    def supports(self, url: str) -> bool:
        return is_x_article_url(url)

    def read(self, context: PlatformContext) -> Any:
        return self.read_article(context, context.normalized_url)

    def read_article(
        self,
        context: PlatformContext,
        article_url: str,
        *,
        response: FetchResponse | None = None,
    ):
        final_url = canonical_x_article_url(article_url) or article_url
        article_id = extract_x_article_id(final_url)
        if context.request.auth_strategy == "user_session_only":
            return self._read_with_user_session(context, final_url)

        response = response or context.fetch_url(final_url)
        extracted = extract_x_article(response.text, final_url)
        if extracted:
            response.final_url = final_url
            return context.build_success_result(response, extracted)

        endpoint_flags = self._try_public_endpoints(context, final_url, article_id)
        flags = ["x_article_body_not_extracted", *endpoint_flags]
        if "LoggedOutShell" in response.text:
            flags.append("x_article_logged_out_shell")
        if context.request.auth_strategy == "user_session_fallback":
            fallback = self._read_with_user_session(context, final_url)
            if fallback:
                return fallback
        return context.build_failure_result(
            final_url,
            self.name,
            "x_article_body_not_extracted",
            _dedupe(flags),
            "X Article body was not present in the logged-out public HTML or public endpoints.",
            "use_local_browser_session_or_provide_article_text",
        )

    def _read_with_user_session(self, context: PlatformContext, final_url: str):
        if context.fetch_user_session_url is None:
            return context.build_failure_result(
                final_url,
                "x_article_authenticated",
                "browser_session_not_available",
                ["browser_session_not_available"],
                "No local user-authorized browser session fetcher is available.",
                "configure_local_browser_session_or_use_anonymous",
            )
        try:
            response = context.fetch_user_session_url(final_url, "x_article")
        except Exception as exc:
            return context.build_failure_result(
                final_url,
                "x_article_authenticated",
                "browser_session_not_available",
                ["browser_session_not_available"],
                str(exc),
                "configure_local_browser_session_or_use_anonymous",
            )

        extracted = extract_x_article(response.text, final_url)
        if extracted:
            extracted.extractor = "x_article_authenticated"
            response.final_url = final_url
            return context.build_success_result(response, extracted)

        extracted = extract_x_article_visible_text(
            response.visible_text,
            final_url,
            page_title=response.headers.get("x-pyaireader-title"),
        )
        if extracted:
            response.final_url = final_url
            return context.build_success_result(response, extracted)

        extracted = _extract_authenticated_article_text(response.text, final_url)
        if extracted:
            response.final_url = final_url
            return context.build_success_result(response, extracted)

        code = (
            "user_session_login_required"
            if _looks_like_login_shell(response.text) or "/i/flow/login" in response.final_url
            else "browser_session_body_not_extracted"
        )
        return context.build_failure_result(
            final_url,
            "x_article_authenticated",
            code,
            [code],
            "The local user-authorized browser session did not expose a readable X Article body.",
            "open_the_article_in_the_local_browser_session_or_provide_article_text",
        )

    def _try_public_endpoints(
        self,
        context: PlatformContext,
        article_url: str,
        article_id: str | None,
    ) -> list[str]:
        flags: list[str] = []
        empty_seen = False
        for endpoint in _public_endpoint_urls(article_url, article_id):
            try:
                response = context.fetch_url(endpoint)
            except Exception:
                continue
            extracted = extract_x_article(response.text, article_url)
            if extracted:
                return flags
            if _looks_empty_public_payload(response.text):
                empty_seen = True
        if empty_seen:
            flags.append("x_article_public_endpoint_empty")
        return flags


def extract_x_article(document: str, url: str | None = None) -> ExtractedText | None:
    state = _extract_initial_state(document)
    if not state:
        return None

    for entity in _article_entities(state):
        title = _first_string(entity, {"title", "headline", "name"})
        author = _first_string(entity, {"author", "screenName", "byline"})
        published_at_raw = _first_string(entity, {"createdAt", "publishedAt", "published_at"})
        body = _article_body(entity)
        if body:
            clean_parts = []
            if title:
                clean_parts.append(title)
            clean_parts.append(body)
            return ExtractedText(
                title=title,
                clean_text="\n\n".join(clean_parts),
                extractor="x_article",
                source="X",
                author=author,
                published_at_raw=published_at_raw,
                primary_text=body,
            )
    return None


def _extract_authenticated_article_text(document: str, url: str) -> ExtractedText | None:
    extracted = TextExtractor().extract(document, url=url)
    clean_text = extracted.clean_text.strip()
    if len(clean_text) < 120:
        return None
    if _looks_like_unreadable_shell(document, clean_text):
        return None
    return ExtractedText(
        title=extracted.title,
        clean_text=clean_text,
        extractor="x_article_authenticated",
        source="X",
        author=extracted.author,
        published_at_raw=extracted.published_at_raw,
        primary_text=clean_text,
    )


def extract_x_article_visible_text(
    visible_text: str,
    url: str | None = None,
    *,
    page_title: str | None = None,
) -> ExtractedText | None:
    lines = [line for line in normalize_text(visible_text).splitlines() if line]
    if len(lines) < 8:
        return None

    title = _title_from_page_title(page_title) or _guess_visible_title(lines)
    if not title:
        return None

    title_index = _find_line_index(lines, title)
    if title_index is None:
        return None

    author = _visible_author(lines, title_index)
    published_at_raw = None
    body_lines: list[str] = []
    in_body = False
    for line in lines[title_index + 1 :]:
        if _is_visible_article_stop(line):
            if _looks_like_x_timestamp(line):
                published_at_raw = line
            break
        if not in_body:
            if _is_visible_article_preamble_noise(line):
                continue
            in_body = True
        body_lines.append(line)

    body = normalize_text("\n".join(body_lines))
    if len(body) < 120:
        return None
    return ExtractedText(
        title=title,
        clean_text=normalize_text(f"{title}\n\n{body}"),
        extractor="x_article_authenticated",
        source="X",
        author=author,
        published_at_raw=published_at_raw,
        primary_text=body,
    )


def _title_from_page_title(page_title: str | None) -> str | None:
    if not page_title:
        return None
    match = re.search(r"[\"“](?P<title>.+?)[\"”]\s*/\s*X$", page_title, flags=re.DOTALL)
    if match:
        return normalize_text(match.group("title"))
    return None


def _guess_visible_title(lines: list[str]) -> str | None:
    handle_index = next((index for index, line in enumerate(lines) if _looks_like_handle(line)), None)
    search_start = handle_index + 1 if handle_index is not None else 0
    for line in lines[search_start:]:
        if _is_visible_article_preamble_noise(line):
            continue
        if _looks_like_handle(line):
            continue
        if len(line) >= 20 and not _looks_like_metric(line):
            return line
    return None


def _find_line_index(lines: list[str], target: str) -> int | None:
    normalized_target = normalize_text(target)
    for index, line in enumerate(lines):
        if normalize_text(line) == normalized_target:
            return index
    return None


def _visible_author(lines: list[str], title_index: int) -> str | None:
    for index in range(title_index - 1, -1, -1):
        line = lines[index]
        if not _looks_like_handle(line):
            continue
        name = None
        if index > 0 and not _is_visible_article_preamble_noise(lines[index - 1]):
            name = lines[index - 1]
        handle = line
        return f"{name} ({handle})" if name else handle
    return None


def _looks_like_handle(line: str) -> bool:
    return re.fullmatch(r"@[A-Za-z0-9_]{1,15}", line or "") is not None


def _looks_like_metric(line: str) -> bool:
    return re.fullmatch(r"[\d,.]+[万KMBkmb]?", line or "") is not None


def _looks_like_x_timestamp(line: str) -> bool:
    if "·" not in line:
        return False
    return bool(re.search(r"\b\d{4}年\d{1,2}月\d{1,2}日\b", line))


def _is_visible_article_stop(line: str) -> bool:
    if _looks_like_x_timestamp(line):
        return True
    return line in {
        "相关",
        "查看引用",
        "发布你的回复",
        "回复",
        "相关用户",
        "当前趋势",
        "有什么新鲜事",
        "显示更多",
        "条款",
    }


def _is_visible_article_preamble_noise(line: str) -> bool:
    if _looks_like_metric(line):
        return True
    return line in {
        "订阅",
        "文章",
        "查看新帖子",
        "对话",
        "主页",
        "探索",
        "通知",
        "关注",
        "聊天",
        "SuperGrok",
        "Premium+",
        "书签",
        "创作者工作室",
        "个人资料",
        "更多",
        "发帖",
    }


def _looks_like_login_shell(text: str) -> bool:
    lowered = (text or "").lower()
    if "loggedoutshell" in lowered:
        return True
    login_markers = [
        "log in",
        "sign up",
        "create your account",
        "don’t miss what’s happening",
        "don't miss what's happening",
    ]
    return sum(1 for marker in login_markers if marker in lowered) >= 2


def _looks_like_unreadable_shell(document: str, clean_text: str) -> bool:
    lowered_doc = (document or "").lower()
    lowered_text = (clean_text or "").lower()
    joined = f"{lowered_doc}\n{lowered_text}"
    if _looks_like_login_shell(joined):
        return True
    unreadable_markers = [
        "javascript is disabled",
        "enable javascript",
        "switch to a supported browser",
        "list of supported browsers",
        "this browser is no longer supported",
    ]
    return any(marker in joined for marker in unreadable_markers)


def _public_endpoint_urls(article_url: str, article_id: str | None) -> list[str]:
    urls = [x_oembed_url(article_url)]
    if article_id:
        urls.append(x_syndication_url(article_id))
    return urls


def _extract_initial_state(document: str) -> dict[str, Any] | None:
    marker = "window.__INITIAL_STATE__"
    index = document.find(marker)
    if index < 0:
        return None
    brace_start = document.find("{", index)
    if brace_start < 0:
        return None
    json_blob = _balanced_json_object(document, brace_start)
    if not json_blob:
        return None
    try:
        parsed = json.loads(json_blob)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _balanced_json_object(document: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(document)):
        char = document[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return document[start : index + 1]
    return None


def _article_entities(state: dict[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for key in ("articleEntities", "publishedArticles"):
        container = state.get(key)
        if not isinstance(container, dict):
            continue
        values = container.get("entities", container)
        if isinstance(values, dict):
            entities.extend(value for value in values.values() if isinstance(value, dict))
        elif isinstance(values, list):
            entities.extend(value for value in values if isinstance(value, dict))
    return entities


def _article_body(entity: dict[str, Any]) -> str | None:
    direct = _first_string(
        entity,
        {
            "body",
            "text",
            "content",
            "markdown",
            "plainText",
            "plain_text",
            "articleText",
            "article_text",
        },
        min_length=40,
    )
    if direct:
        return direct

    parts = _collect_text_parts(entity)
    body = "\n".join(_dedupe(part for part in parts if _is_body_text(part)))
    return body if len(body) >= 40 else None


def _first_string(obj: dict[str, Any], keys: set[str], *, min_length: int = 1) -> str | None:
    lowered = {key.lower() for key in keys}
    for key, value in obj.items():
        if key.lower() in lowered and isinstance(value, str):
            text = value.strip()
            if len(text) >= min_length:
                return text
    return None


def _collect_text_parts(obj: Any) -> list[str]:
    parts: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = key.lower()
            if lowered in {"text", "content", "plaintext", "plain_text", "body"} and isinstance(
                value, str
            ):
                parts.append(value.strip())
            elif lowered in {"blocks", "paragraphs", "sections", "children", "items"}:
                parts.extend(_collect_text_parts(value))
    elif isinstance(obj, list):
        for item in obj:
            parts.extend(_collect_text_parts(item))
    return parts


def _is_body_text(text: str) -> bool:
    if len(text) < 20:
        return False
    lowered = text.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return False
    return True


def _looks_empty_public_payload(text: str) -> bool:
    value = (text or "").strip()
    return value in {"", "{}", "[]", "null"}


def _dedupe(items) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item and item not in seen:
            output.append(item)
            seen.add(item)
    return output
