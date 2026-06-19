from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse


@dataclass
class ExtractedText:
    title: str | None
    clean_text: str
    extractor: str
    source: str | None = None
    author: str | None = None
    published_at_raw: str | None = None
    published_at_utc: str | None = None
    primary_text: str | None = None


class TextExtractor:
    def extract(self, document: str, url: str | None = None) -> ExtractedText:
        social = self._try_social(document, url)
        if social:
            return social

        trafilatura = self._try_trafilatura(document, url)
        if trafilatura and len(trafilatura.clean_text) >= 200:
            return trafilatura

        parsed = _SimpleHTMLTextParser()
        parsed.feed(document)
        text = normalize_text("\n".join(parsed.text_parts))
        title = normalize_text(parsed.title or "") or None
        return ExtractedText(title=title, clean_text=text, extractor="htmlparser")

    def _try_trafilatura(self, document: str, url: str | None) -> ExtractedText | None:
        try:
            import trafilatura  # type: ignore
        except Exception:
            return None

        extracted = trafilatura.extract(
            document,
            url=url,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            include_links=False,
        )
        if not extracted:
            return None

        title = None
        try:
            metadata = trafilatura.extract_metadata(document)
            title = getattr(metadata, "title", None) if metadata else None
        except Exception:
            title = None

        return ExtractedText(
            title=normalize_text(title or "") or None,
            clean_text=normalize_text(extracted),
            extractor="trafilatura",
        )

    def _try_social(self, document: str, url: str | None) -> ExtractedText | None:
        if not _is_x_status_url(url):
            return None
        return _extract_x_status(document, url)


def _is_x_status_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"} and "/status/" in parsed.path


def _extract_x_status(document: str, url: str | None) -> ExtractedText | None:
    parsed = _SocialHTMLParser()
    parsed.feed(document)
    title = normalize_text(parsed.title or "") or None
    metadata = {key.lower(): normalize_text(value) for key, value in parsed.metadata.items()}
    text_lines = [line for line in normalize_text("\n".join(parsed.text_parts)).splitlines() if line]

    candidates = [
        metadata.get("og:title"),
        metadata.get("twitter:title"),
        title,
        metadata.get("description"),
        metadata.get("og:description"),
        metadata.get("twitter:description"),
    ]
    author, body = _tweet_from_candidates([candidate for candidate in candidates if candidate])
    if not body:
        return None

    handle = _extract_handle(text_lines, url)
    display_author = _format_author(author, handle)
    published_at_raw = _extract_published_at(text_lines)
    metrics = _extract_x_metrics(text_lines)

    clean_lines = [body]
    if display_author:
        clean_lines.append(f"Author: {display_author}")
    if published_at_raw:
        clean_lines.append(f"Published: {published_at_raw}")
    clean_lines.extend(metrics)

    return ExtractedText(
        title=title,
        clean_text=normalize_text("\n".join(clean_lines)),
        extractor="x_status",
        source="X",
        author=display_author or author,
        published_at_raw=published_at_raw,
        primary_text=body,
    )


class _SocialHTMLParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.metadata: dict[str, str] = {}
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = attr_map.get("property") or attr_map.get("name")
            content = attr_map.get("content")
            if key and content:
                self.metadata[key] = content
        if tag in _SimpleHTMLTextParser.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in _SimpleHTMLTextParser.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        if data.strip():
            self.text_parts.append(data)


def _tweet_from_candidates(candidates: list[str]) -> tuple[str | None, str | None]:
    for candidate in candidates:
        author, body = _tweet_from_title(candidate)
        if body:
            return author, body
    return None, None


def _tweet_from_title(value: str) -> tuple[str | None, str | None]:
    value = normalize_text(value)
    match = re.match(
        r"^(?P<author>.+?)\s+on\s+(?:X|Twitter):\s+[\"“](?P<body>.+?)[\"”]\s*/\s*(?:X|Twitter)$",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return normalize_text(match.group("author")), normalize_text(match.group("body"))

    quoted = re.search(r"[\"“](?P<body>.+?)[\"”]", value, flags=re.DOTALL)
    if quoted:
        return None, normalize_text(quoted.group("body"))
    return None, None


def _extract_handle(lines: list[str], url: str | None) -> str | None:
    for line in lines:
        match = re.search(r"@([A-Za-z0-9_]{1,15})\b", line)
        if match:
            return f"@{match.group(1)}"
    if url:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return f"@{parts[0]}"
    return None


def _format_author(author: str | None, handle: str | None) -> str | None:
    if author and handle:
        return f"{author} ({handle})"
    return author or handle


def _extract_published_at(lines: list[str]) -> str | None:
    for line in lines:
        if re.search(r"\b\d{4}年\d{1,2}月\d{1,2}日\b", line):
            return line
        if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b", line):
            return line
    return None


def _extract_x_metrics(lines: list[str]) -> list[str]:
    metrics: list[str] = []
    for index, line in enumerate(lines):
        lowered = line.lower()
        if lowered in {"views", "replies"} and index > 0:
            metrics.append(f"{line.title()}: {lines[index - 1]}")
        elif lowered.startswith("read ") and "repl" in lowered:
            metrics.append(line)
    return _dedupe_adjacent(metrics)


class _SimpleHTMLTextParser(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "main",
        "section",
        "p",
        "div",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "tr",
        "table",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe", "nav", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.title: str = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        if data.strip():
            self.text_parts.append(data)


def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(_dedupe_adjacent(lines)).strip()


def _dedupe_adjacent(lines: list[str]) -> list[str]:
    output: list[str] = []
    previous = None
    for line in lines:
        if line != previous:
            output.append(line)
        previous = line
    return output
