from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_STORE_CONFIG_PATH = Path.home() / ".pyaireader" / "stores.toml"
DEFAULT_LIBRARY_PATH = Path.home() / ".pyaireader" / "library.sqlite3"


@dataclass(frozen=True)
class StoreDefinition:
    name: str
    driver: str
    path: Path
    format: str = "json"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "driver": self.driver,
            "path": str(self.path),
            "format": self.format,
        }


@dataclass(frozen=True)
class StorageConfig:
    config_path: Path
    stores: dict[str, StoreDefinition]
    loaded_from_file: bool = False

    @classmethod
    def from_env(cls) -> "StorageConfig":
        config_path = Path(os.getenv("PYAIREADER_STORES_CONFIG", str(DEFAULT_STORE_CONFIG_PATH)))
        if config_path.exists():
            return cls.from_file(config_path)
        return cls(
            config_path=config_path,
            stores={
                "default": StoreDefinition(
                    name="default",
                    driver="sqlite",
                    path=Path(
                        os.getenv("PYAIREADER_LIBRARY_PATH", str(DEFAULT_LIBRARY_PATH))
                    ).expanduser(),
                    format="json",
                )
            },
            loaded_from_file=False,
        )

    @classmethod
    def from_file(cls, path: Path) -> "StorageConfig":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        stores_data = data.get("stores")
        if not isinstance(stores_data, dict) or not stores_data:
            raise ValueError("stores.toml must contain at least one [stores.<name>] section")

        stores: dict[str, StoreDefinition] = {}
        for name, raw in stores_data.items():
            if not isinstance(raw, dict):
                raise ValueError(f"store {name!r} must be a table")
            driver = str(raw.get("driver", "")).strip()
            if not driver:
                raise ValueError(f"store {name!r} requires driver")
            if driver in {"http", "postgres", "vector_store", "custom_command"}:
                raise ValueError(f"store driver {driver!r} is reserved but not implemented")
            if driver not in {"sqlite", "filesystem"}:
                raise ValueError(f"unsupported store driver: {driver}")
            raw_path = raw.get("path")
            if not raw_path:
                raise ValueError(f"store {name!r} requires path")
            stores[name] = StoreDefinition(
                name=name,
                driver=driver,
                path=Path(str(raw_path)).expanduser(),
                format=str(raw.get("format", "json")).strip().lower() or "json",
                raw=dict(raw),
            )
        if "default" not in stores:
            stores["default"] = StoreDefinition(
                name="default",
                driver="sqlite",
                path=Path(os.getenv("PYAIREADER_LIBRARY_PATH", str(DEFAULT_LIBRARY_PATH))).expanduser(),
                format="json",
            )
        return cls(config_path=path, stores=stores, loaded_from_file=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_path": str(self.config_path),
            "loaded_from_file": self.loaded_from_file,
            "stores": {name: store.to_dict() for name, store in self.stores.items()},
        }
