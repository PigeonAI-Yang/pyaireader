from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class CacheWritePolicy:
    name: str
    should_write: bool
    ttl_seconds: int = 0


class SQLiteReaderCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def get(self, cache_key: str) -> dict | None:
        now = _now_iso()
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                """
                SELECT result_json, cached_at
                FROM reader_cache
                WHERE cache_key = ? AND expires_at > ?
                """,
                (cache_key, now),
            ).fetchone()
        if not row:
            return None
        result_json, cached_at = row
        result = json.loads(result_json)
        result["cached_at"] = cached_at
        return result

    def set(
        self,
        cache_key: str,
        normalized_url: str,
        result: dict,
        *,
        ttl_seconds: int,
        cache_policy: str,
    ) -> None:
        cached_at = _now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
        payload = json.dumps(result, ensure_ascii=False)
        trace = result.get("trace") or {}
        quality = result.get("quality") or {}
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO reader_cache(
                    cache_key, normalized_url, final_url, domain, result_json,
                    quality_score, quality_level, content_hash, raw_html_hash,
                    cache_policy, fetched_at, cached_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    normalized_url = excluded.normalized_url,
                    final_url = excluded.final_url,
                    domain = excluded.domain,
                    result_json = excluded.result_json,
                    quality_score = excluded.quality_score,
                    quality_level = excluded.quality_level,
                    content_hash = excluded.content_hash,
                    raw_html_hash = excluded.raw_html_hash,
                    cache_policy = excluded.cache_policy,
                    fetched_at = excluded.fetched_at,
                    cached_at = excluded.cached_at,
                    expires_at = excluded.expires_at
                """,
                (
                    cache_key,
                    normalized_url,
                    result.get("final_url"),
                    result.get("domain"),
                    payload,
                    quality.get("score"),
                    quality.get("level"),
                    result.get("content_hash") or trace.get("content_hash"),
                    result.get("raw_html_hash") or trace.get("raw_html_hash"),
                    cache_policy,
                    result.get("fetched_at"),
                    cached_at,
                    expires_at,
                ),
            )
            conn.commit()

    def clear(self, normalized_url: str | None = None, domain: str | None = None) -> int:
        with sqlite3.connect(self.path) as conn:
            if normalized_url:
                cursor = conn.execute("DELETE FROM reader_cache WHERE normalized_url = ?", (normalized_url,))
            elif domain:
                cursor = conn.execute("DELETE FROM reader_cache WHERE domain = ?", (domain,))
            else:
                cursor = conn.execute("DELETE FROM reader_cache")
            conn.commit()
            return cursor.rowcount

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            if self._has_incompatible_schema(conn):
                conn.execute("DROP TABLE IF EXISTS reader_cache")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reader_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL UNIQUE,
                    normalized_url TEXT NOT NULL,
                    final_url TEXT,
                    domain TEXT,
                    result_json TEXT NOT NULL,
                    quality_score REAL,
                    quality_level TEXT,
                    content_hash TEXT,
                    raw_html_hash TEXT,
                    cache_policy TEXT,
                    fetched_at TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reader_cache_url ON reader_cache(normalized_url)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reader_cache_domain ON reader_cache(domain)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reader_cache_expires ON reader_cache(expires_at)"
            )
            conn.commit()

    def _has_incompatible_schema(self, conn: sqlite3.Connection) -> bool:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reader_cache'"
        ).fetchone()
        if not table_exists:
            return False
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(reader_cache)").fetchall()
        }
        required = {"cache_key", "normalized_url", "result_json", "cached_at", "expires_at"}
        return not required.issubset(columns)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
