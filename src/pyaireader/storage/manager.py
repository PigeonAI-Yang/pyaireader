from __future__ import annotations

from typing import Any

from pyaireader.models import ReadingItem, reading_item_from_dict
from pyaireader.storage.base import StorageBackend, StorageSaveResult
from pyaireader.storage.config import StorageConfig, StoreDefinition
from pyaireader.storage.filesystem_store import FilesystemStorageBackend
from pyaireader.storage.sqlite_store import SQLiteStorageBackend


class StorageManager:
    def __init__(self, config: StorageConfig | None = None) -> None:
        self.config = config or StorageConfig.from_env()
        self._backends: dict[str, StorageBackend] = {}

    @classmethod
    def from_env(cls) -> "StorageManager":
        return cls(StorageConfig.from_env())

    def status(self) -> dict[str, Any]:
        stores = []
        for name, definition in self.config.stores.items():
            try:
                stores.append(self._get_backend(name).status())
            except Exception as exc:
                stores.append(
                    {
                        **definition.to_dict(),
                        "available": False,
                        "error": str(exc),
                    }
                )
        return {
            "success": True,
            "config_path": str(self.config.config_path),
            "loaded_from_file": self.config.loaded_from_file,
            "default_store": "default",
            "stores": stores,
            "reserved_drivers": ["http", "postgres", "vector_store", "custom_command"],
        }

    def save(self, item: ReadingItem | dict[str, Any], *, store: str = "default") -> StorageSaveResult:
        reading_item = item if isinstance(item, ReadingItem) else reading_item_from_dict(item)
        return self._get_backend(store).save(reading_item)

    def get(self, item_id: str, *, store: str = "default") -> dict[str, Any]:
        item = self._get_backend(store).get(item_id)
        if not item:
            return {
                "success": False,
                "store": store,
                "item_id": item_id,
                "item": None,
                "error": {
                    "code": "not_found",
                    "message": f"reading item not found: {item_id}",
                    "retryable": False,
                    "suggested_next_action": "check_item_id_or_store",
                    "type": "NotFound",
                },
            }
        return {"success": True, "store": store, "item_id": item_id, "item": item.to_dict()}

    def list(
        self,
        *,
        store: str = "default",
        limit: int = 20,
        offset: int = 0,
        project: str | None = None,
        include_text: bool = False,
    ) -> dict[str, Any]:
        items = self._get_backend(store).list(limit=limit, offset=offset, project=project)
        return {
            "success": True,
            "store": store,
            "count": len(items),
            "items": [_item_payload(item, include_text=include_text) for item in items],
        }

    def search(
        self,
        query: str,
        *,
        store: str = "default",
        limit: int = 20,
        project: str | None = None,
        include_text: bool = False,
    ) -> dict[str, Any]:
        items = self._get_backend(store).search(query, limit=limit, project=project)
        return {
            "success": True,
            "store": store,
            "query": query,
            "count": len(items),
            "items": [_item_payload(item, include_text=include_text) for item in items],
        }

    def export(self, item_id: str, *, store: str = "default", format: str = "json") -> dict[str, Any]:
        content = self._get_backend(store).export(item_id, format=format)
        return {
            "success": True,
            "store": store,
            "item_id": item_id,
            "format": "md" if format == "markdown" else format,
            "content": content,
        }

    def _get_backend(self, name: str) -> StorageBackend:
        if name in self._backends:
            return self._backends[name]
        definition = self.config.stores.get(name)
        if not definition:
            raise KeyError(f"unknown store: {name}")
        backend = _build_backend(definition)
        self._backends[name] = backend
        return backend


def _build_backend(definition: StoreDefinition) -> StorageBackend:
    if definition.driver == "sqlite":
        return SQLiteStorageBackend(definition.name, definition.path)
    if definition.driver == "filesystem":
        return FilesystemStorageBackend(
            definition.name,
            definition.path,
            format=definition.format,
        )
    raise ValueError(f"unsupported store driver: {definition.driver}")


def _item_payload(item: ReadingItem, *, include_text: bool) -> dict[str, Any]:
    payload = item.to_dict()
    if include_text:
        return payload
    text = payload.pop("clean_text", "")
    payload["clean_text_length"] = len(text)
    payload["clean_text_preview"] = text[:300].strip()
    return payload
