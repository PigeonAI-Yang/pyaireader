from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from pyaireader.errors import UnsafeUrlError


ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_SCHEMES = {"file", "ftp", "data", "javascript"}
MAX_URL_LENGTH = 4096


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise UnsafeUrlError("URL is required")
    if len(raw) > MAX_URL_LENGTH:
        raise UnsafeUrlError("URL is too long")

    parsed = urlparse(raw)
    if not parsed.scheme:
        parsed = urlparse(f"https://{raw}")

    scheme = parsed.scheme.lower()
    if scheme in BLOCKED_SCHEMES or scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"Unsupported URL scheme: {scheme}")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs with userinfo are not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL must include a hostname")

    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise UnsafeUrlError("Localhost URLs are not allowed")
    port = parsed.port
    netloc = hostname
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{hostname}:{port}"

    normalized = parsed._replace(scheme=scheme, netloc=netloc, fragment="")
    return urlunparse(normalized)


def extract_domain(url: str) -> str | None:
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else None
