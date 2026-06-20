from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol

from pyaireader.models import ReadingItem


@dataclass(frozen=True)
class StorageCapabilities:
    can_save: bool = True
    can_get: bool = True
    can_list: bool = True
    can_search: bool = True
    can_delete: bool = False
    can_export: bool = True

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class StorageSaveResult:
    success: bool
    store: str
    item_id: str
    created: bool
    item: ReadingItem | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "store": self.store,
            "item_id": self.item_id,
            "created": self.created,
            "item": self.item.to_dict() if self.item else None,
            "error": self.error,
        }


class StorageBackend(Protocol):
    name: str
    driver: str
    capabilities: StorageCapabilities

    def status(self) -> dict:
        ...

    def save(self, item: ReadingItem) -> StorageSaveResult:
        ...

    def get(self, item_id: str) -> ReadingItem | None:
        ...

    def list(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        project: str | None = None,
    ) -> list[ReadingItem]:
        ...

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        project: str | None = None,
    ) -> list[ReadingItem]:
        ...

    def export(self, item_id: str, *, format: str = "json") -> str:
        ...
