from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pyaireader.models import ReadingItem, reading_item_from_dict
from pyaireader.storage.base import StorageCapabilities, StorageSaveResult


class SQLiteStorageBackend:
    driver = "sqlite"
    capabilities = StorageCapabilities()

    def __init__(self, name: str, path: Path) -> None:
        self.name = name
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def status(self) -> dict:
        return {
            "name": self.name,
            "driver": self.driver,
            "path": str(self.path),
            "available": True,
            "capabilities": self.capabilities.to_dict(),
        }

    def save(self, item: ReadingItem) -> StorageSaveResult:
        payload = json.dumps(item.to_dict(), ensure_ascii=False)
        dedupe_key = _dedupe_key(item)
        with sqlite3.connect(self.path) as conn:
            existing = conn.execute(
                "SELECT id, item_json FROM reading_items WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            if existing:
                existing_item = reading_item_from_dict(json.loads(existing[1]))
                return StorageSaveResult(
                    success=True,
                    store=self.name,
                    item_id=existing[0],
                    created=False,
                    item=existing_item,
                )
            conn.execute(
                """
                INSERT INTO reading_items(
                    id, dedupe_key, source_url, final_url, title, author,
                    published_at_raw, project, tags_json, content_hash,
                    created_at, item_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    dedupe_key,
                    item.source_url,
                    item.final_url,
                    item.title,
                    item.author,
                    item.published_at_raw,
                    item.project,
                    json.dumps(item.tags, ensure_ascii=False),
                    item.content_hash,
                    item.created_at,
                    payload,
                ),
            )
            conn.commit()
        return StorageSaveResult(
            success=True,
            store=self.name,
            item_id=item.id,
            created=True,
            item=item,
        )

    def get(self, item_id: str) -> ReadingItem | None:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT item_json FROM reading_items WHERE id = ?",
                (item_id,),
            ).fetchone()
        if not row:
            return None
        return reading_item_from_dict(json.loads(row[0]))

    def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        project: str | None = None,
    ) -> list[ReadingItem]:
        sql = "SELECT item_json FROM reading_items"
        params: list[object] = []
        if project:
            sql += " WHERE project = ?"
            params.append(project)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [reading_item_from_dict(json.loads(row[0])) for row in rows]

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        project: str | None = None,
    ) -> list[ReadingItem]:
        needle = f"%{query.lower()}%"
        params: list[object] = [needle, needle, needle, needle]
        sql = """
            SELECT item_json
            FROM reading_items
            WHERE (
                lower(coalesce(title, '')) LIKE ?
                OR lower(source_url) LIKE ?
                OR lower(coalesce(author, '')) LIKE ?
                OR lower(item_json) LIKE ?
            )
        """
        if project:
            sql += " AND project = ?"
            params.append(project)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [reading_item_from_dict(json.loads(row[0])) for row in rows]

    def export(self, item_id: str, *, format: str = "json") -> str:
        item = self.get(item_id)
        if not item:
            raise KeyError(f"reading item not found: {item_id}")
        if format == "json":
            return json.dumps(item.to_dict(), ensure_ascii=False, indent=2)
        if format in {"md", "markdown"}:
            return _item_to_markdown(item)
        raise ValueError("format must be 'json' or 'md'")

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reading_items (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    source_url TEXT NOT NULL,
                    final_url TEXT,
                    title TEXT,
                    author TEXT,
                    published_at_raw TEXT,
                    project TEXT,
                    tags_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    item_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reading_items_source_url ON reading_items(source_url)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reading_items_project ON reading_items(project)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reading_items_created_at ON reading_items(created_at)"
            )
            conn.commit()


def _dedupe_key(item: ReadingItem) -> str:
    return f"{item.source_url}\n{item.content_hash}"


def _item_to_markdown(item: ReadingItem) -> str:
    title = item.title or item.source_url
    lines = [
        f"# {title}",
        "",
        f"- Source: {item.source_url}",
        f"- Final URL: {item.final_url or ''}",
        f"- Author: {item.author or ''}",
        f"- Published: {item.published_at_raw or ''}",
        f"- Project: {item.project or ''}",
        f"- Tags: {', '.join(item.tags)}",
        f"- Content Hash: {item.content_hash}",
        "",
        item.clean_text.strip(),
        "",
    ]
    return "\n".join(lines)
