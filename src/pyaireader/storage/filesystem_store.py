from __future__ import annotations

import json
from pathlib import Path

from pyaireader.models import ReadingItem, reading_item_from_dict
from pyaireader.storage.base import StorageCapabilities, StorageSaveResult
from pyaireader.storage.sqlite_store import _item_to_markdown


class FilesystemStorageBackend:
    driver = "filesystem"
    capabilities = StorageCapabilities()

    def __init__(self, name: str, path: Path, *, format: str = "json") -> None:
        self.name = name
        self.path = path
        self.format = format
        self.path.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        return {
            "name": self.name,
            "driver": self.driver,
            "path": str(self.path),
            "format": self.format,
            "available": True,
            "capabilities": self.capabilities.to_dict(),
        }

    def save(self, item: ReadingItem) -> StorageSaveResult:
        existing = self._find_existing(item)
        if existing:
            return StorageSaveResult(
                success=True,
                store=self.name,
                item_id=existing.id,
                created=False,
                item=existing,
            )

        self._json_path(item.id).write_text(
            json.dumps(item.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if self.format in {"md", "markdown"}:
            self._markdown_path(item.id).write_text(_item_to_markdown(item), encoding="utf-8")
        return StorageSaveResult(
            success=True,
            store=self.name,
            item_id=item.id,
            created=True,
            item=item,
        )

    def get(self, item_id: str) -> ReadingItem | None:
        path = self._json_path(item_id)
        if not path.exists():
            return None
        return reading_item_from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        project: str | None = None,
    ) -> list[ReadingItem]:
        items = self._read_all_items()
        if project:
            items = [item for item in items if item.project == project]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[offset : offset + limit]

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        project: str | None = None,
    ) -> list[ReadingItem]:
        needle = query.lower()
        matches: list[ReadingItem] = []
        for item in self._read_all_items():
            if project and item.project != project:
                continue
            haystack = "\n".join(
                [
                    item.title or "",
                    item.source_url,
                    item.author or "",
                    item.clean_text,
                    json.dumps(item.metadata, ensure_ascii=False),
                ]
            ).lower()
            if needle in haystack:
                matches.append(item)
        matches.sort(key=lambda item: item.created_at, reverse=True)
        return matches[:limit]

    def export(self, item_id: str, *, format: str = "json") -> str:
        item = self.get(item_id)
        if not item:
            raise KeyError(f"reading item not found: {item_id}")
        if format == "json":
            return json.dumps(item.to_dict(), ensure_ascii=False, indent=2)
        if format in {"md", "markdown"}:
            return _item_to_markdown(item)
        raise ValueError("format must be 'json' or 'md'")

    def _find_existing(self, item: ReadingItem) -> ReadingItem | None:
        for existing in self._read_all_items():
            if existing.source_url == item.source_url and existing.content_hash == item.content_hash:
                return existing
        return None

    def _read_all_items(self) -> list[ReadingItem]:
        items: list[ReadingItem] = []
        for path in self.path.glob("*.json"):
            try:
                items.append(reading_item_from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return items

    def _json_path(self, item_id: str) -> Path:
        return self.path / f"{item_id}.json"

    def _markdown_path(self, item_id: str) -> Path:
        return self.path / f"{item_id}.md"
