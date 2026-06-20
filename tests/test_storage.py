from __future__ import annotations

import json
from pathlib import Path

from pyaireader.cache import SQLiteReaderCache
from pyaireader.config import ReaderConfig
from pyaireader.fetchers import FetchResponse
from pyaireader.models import (
    READING_ITEM_SCHEMA_VERSION,
    ReadUrlRequest,
    reading_item_from_read_result,
)
from pyaireader.reader import ReaderPipeline
from pyaireader.storage import StorageConfig, StorageManager, StoreDefinition


HTML = """
<!doctype html>
<html>
  <head><title>AI 数据中心订单</title></head>
  <body>
    <article>
      <h1>AI 数据中心订单</h1>
      <p>测试公司公告称，公司获得 AI 数据中心电力设备订单，金额为12.5亿元。</p>
      <p>公司预计上半年净利润同比增长45%至60%，订单来自北美云厂商。</p>
    </article>
  </body>
</html>
"""


class FakeFetcher:
    name = "fake_http"

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(
            url=url,
            final_url=url,
            status_code=200,
            content_type="text/html; charset=utf-8",
            text=HTML,
            raw=HTML.encode("utf-8"),
            elapsed_ms=1,
        )


def test_pipeline_save_to_default_sqlite_and_read_back(tmp_path: Path) -> None:
    pipeline = _pipeline_with_sqlite_store(tmp_path)

    result = pipeline.read(
        ReadUrlRequest(
            url="https://example.com/order",
            save=True,
            project="research",
            tags=["ai", "datacenter"],
        )
    )

    assert result.success is True
    assert result.saved is True
    assert result.saved_item_id
    assert result.saved_to == "default"

    stored = pipeline.library_get(result.saved_item_id)
    assert stored["success"] is True
    item = stored["item"]
    assert item["schema_version"] == READING_ITEM_SCHEMA_VERSION
    assert item["project"] == "research"
    assert item["tags"] == ["ai", "datacenter"]
    assert "12.5亿元" in item["clean_text"]

    search = pipeline.library_search("北美云厂商")
    assert search["success"] is True
    assert search["count"] == 1
    assert search["items"][0]["id"] == result.saved_item_id
    assert "clean_text" not in search["items"][0]

    exported_md = pipeline.library_export(result.saved_item_id, format="md")
    assert exported_md["success"] is True
    assert "# AI 数据中心订单" in exported_md["content"]
    assert "净利润同比增长45%至60%" in exported_md["content"]

    exported_json = pipeline.library_export(result.saved_item_id, format="json")
    exported_payload = json.loads(exported_json["content"])
    assert exported_payload["id"] == result.saved_item_id


def test_pipeline_save_is_idempotent_even_from_cache(tmp_path: Path) -> None:
    pipeline = _pipeline_with_sqlite_store(tmp_path)

    first = pipeline.read(ReadUrlRequest(url="https://example.com/order", save=True))
    second = pipeline.read(ReadUrlRequest(url="https://example.com/order", save=True))

    assert first.saved_item_id == second.saved_item_id
    assert second.trace and second.trace.cache_hit is True
    listing = pipeline.library_list()
    assert listing["count"] == 1


def test_failed_read_is_not_saved(tmp_path: Path) -> None:
    pipeline = _pipeline_with_sqlite_store(tmp_path)

    result = pipeline.read(ReadUrlRequest(url="http://127.0.0.1/private", save=True))

    assert result.success is False
    assert result.saved is False
    assert result.saved_item_id is None
    assert pipeline.library_list()["count"] == 0


def test_filesystem_store_writes_json_and_markdown(tmp_path: Path) -> None:
    pipeline = _pipeline_with_sqlite_store(tmp_path)
    read_result = pipeline.read(ReadUrlRequest(url="https://example.com/order", bypass_cache=True))
    item = reading_item_from_read_result(read_result, project="vault", tags=["fs"])
    vault = tmp_path / "vault"
    manager = StorageManager(
        StorageConfig(
            config_path=tmp_path / "stores.toml",
            stores={
                "default": StoreDefinition(
                    name="default",
                    driver="filesystem",
                    path=vault,
                    format="markdown",
                )
            },
        )
    )

    saved = manager.save(item)

    assert saved.success is True
    assert (vault / f"{item.id}.json").exists()
    assert (vault / f"{item.id}.md").exists()
    assert manager.get(item.id)["item"]["clean_text"] == item.clean_text
    assert manager.search("电力设备")["items"][0]["id"] == item.id


def _pipeline_with_sqlite_store(tmp_path: Path) -> ReaderPipeline:
    config = ReaderConfig(cache_path=tmp_path / "cache.sqlite3")
    storage_manager = StorageManager(
        StorageConfig(
            config_path=tmp_path / "stores.toml",
            stores={
                "default": StoreDefinition(
                    name="default",
                    driver="sqlite",
                    path=tmp_path / "library.sqlite3",
                )
            },
        )
    )
    return ReaderPipeline(
        config=config,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
        cache=SQLiteReaderCache(config.cache_path),
        storage_manager=storage_manager,
    )
