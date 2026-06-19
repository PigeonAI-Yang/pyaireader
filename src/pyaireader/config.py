from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReaderConfig:
    cache_path: Path
    fetch_timeout_seconds: float = 20.0
    cache_ttl_seconds: int = 24 * 60 * 60
    weak_ttl_seconds: int = 30 * 60
    not_found_ttl_seconds: int = 60 * 60
    diagnostic_ttl_seconds: int = 30 * 60
    max_total_chars: int = 16000
    max_clean_text_chars: int = 12000
    max_evidence_items: int = 12
    max_number_mentions: int = 30
    max_date_mentions: int = 30
    max_entity_items: int = 40
    max_redirects: int = 5
    per_domain_concurrency: int = 1
    per_domain_min_interval_ms: int = 1000
    enable_scrapling: bool = False
    enable_browser: bool = False
    enable_pdf: bool = False
    block_private_network: bool = True

    @classmethod
    def default(cls) -> "ReaderConfig":
        return cls.from_env()

    @classmethod
    def from_env(cls) -> "ReaderConfig":
        base = Path.home() / ".pyaireader"
        return cls(
            cache_path=Path(os.getenv("PYAIREADER_CACHE_PATH", str(base / "reader_cache.sqlite3"))),
            fetch_timeout_seconds=_float_env("PYAIREADER_HTTP_TIMEOUT_SECONDS", 20.0),
            cache_ttl_seconds=_int_env("PYAIREADER_DEFAULT_TTL_SECONDS", 24 * 60 * 60),
            weak_ttl_seconds=_int_env("PYAIREADER_WEAK_TTL_SECONDS", 30 * 60),
            not_found_ttl_seconds=_int_env("PYAIREADER_NOT_FOUND_TTL_SECONDS", 60 * 60),
            diagnostic_ttl_seconds=_int_env("PYAIREADER_DIAGNOSTIC_TTL_SECONDS", 30 * 60),
            max_total_chars=_int_env("PYAIREADER_MAX_TOTAL_CHARS", 16000),
            max_clean_text_chars=_int_env("PYAIREADER_MAX_CLEAN_TEXT_CHARS", 12000),
            max_evidence_items=_int_env("PYAIREADER_MAX_EVIDENCE_ITEMS", 12),
            max_number_mentions=_int_env("PYAIREADER_MAX_NUMBER_MENTIONS", 30),
            max_date_mentions=_int_env("PYAIREADER_MAX_DATE_MENTIONS", 30),
            max_entity_items=_int_env("PYAIREADER_MAX_ENTITY_ITEMS", 40),
            max_redirects=_int_env("PYAIREADER_MAX_REDIRECTS", 5),
            per_domain_concurrency=_int_env("PYAIREADER_PER_DOMAIN_CONCURRENCY", 1),
            per_domain_min_interval_ms=_int_env("PYAIREADER_PER_DOMAIN_MIN_INTERVAL_MS", 1000),
            enable_scrapling=_bool_env("PYAIREADER_ENABLE_SCRAPLING", False),
            enable_browser=_bool_env("PYAIREADER_ENABLE_BROWSER", False),
            enable_pdf=_bool_env("PYAIREADER_ENABLE_PDF", False),
            block_private_network=_bool_env("PYAIREADER_BLOCK_PRIVATE_NETWORK", True),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None else int(raw)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None else float(raw)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
