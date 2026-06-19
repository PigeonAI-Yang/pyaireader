from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ContentVersion:
    normalized_url: str
    content_hash: str
    fetched_at: str
    changed: bool


class ContentVersionStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def record(self, normalized_url: str, content_hash: str, fetched_at: str | None = None) -> ContentVersion:
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        latest = self.latest(normalized_url)
        changed = latest is None or latest.content_hash != content_hash
        if changed:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    """
                    INSERT INTO content_versions(normalized_url, content_hash, fetched_at)
                    VALUES (?, ?, ?)
                    """,
                    (normalized_url, content_hash, fetched_at),
                )
                conn.commit()
        return ContentVersion(
            normalized_url=normalized_url,
            content_hash=content_hash,
            fetched_at=fetched_at,
            changed=changed,
        )

    def latest(self, normalized_url: str) -> ContentVersion | None:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                """
                SELECT normalized_url, content_hash, fetched_at
                FROM content_versions
                WHERE normalized_url = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (normalized_url,),
            ).fetchone()
        if not row:
            return None
        return ContentVersion(
            normalized_url=row[0],
            content_hash=row[1],
            fetched_at=row[2],
            changed=False,
        )

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS content_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_url TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_content_versions_url ON content_versions(normalized_url)"
            )
            conn.commit()
