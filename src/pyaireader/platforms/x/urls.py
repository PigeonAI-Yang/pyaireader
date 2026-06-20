from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}


def is_x_status_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in X_HOSTS and re.search(r"/status/\d+", parsed.path) is not None


def is_x_article_url(url: str | None) -> bool:
    return extract_x_article_id(url) is not None


def is_tco_url(url: str | None) -> bool:
    if not url:
        return False
    return (urlparse(url).hostname or "").lower() == "t.co"


def extract_x_article_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in X_HOSTS:
        return None
    match = re.search(r"^/i/article/(?P<id>\d+)", parsed.path)
    return match.group("id") if match else None


def canonical_x_article_url(url: str) -> str | None:
    article_id = extract_x_article_id(url)
    if not article_id:
        return None
    return f"https://x.com/i/article/{article_id}"


def find_x_article_url(text: str) -> str | None:
    pattern = re.compile(
        r"https?://(?:x\.com|twitter\.com)/i/article/\d{10,}|(?<![\w/])/i/article/\d{10,}",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text or "")
    if not match:
        return None
    value = match.group(0)
    if value.startswith("/"):
        value = f"https://x.com{value}"
    return canonical_x_article_url(value)


def extract_only_url(text: str | None) -> str | None:
    value = (text or "").strip().strip("\"'“”")
    value = re.sub(r"\s+", " ", value)
    match = re.fullmatch(r"https?://[^\s<>]+", value)
    if not match:
        return None
    return value.rstrip(").,;")


def x_oembed_url(article_url: str) -> str:
    return "https://publish.x.com/oembed?" + urlencode({"url": article_url})


def x_syndication_url(article_id: str, *, lang: str = "en") -> str:
    query = urlencode({"id": article_id, "lang": lang})
    return urlunparse(("https", "cdn.syndication.twimg.com", "/tweet-result", "", query, ""))


def x_status_url_from_oembed_request(url: str) -> str | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != "publish.x.com":
        return None
    values = parse_qs(parsed.query).get("url") or []
    return values[0] if values else None
