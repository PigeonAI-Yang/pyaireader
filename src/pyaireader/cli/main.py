from __future__ import annotations

import argparse
import json
import sys

from pyaireader.browser_sessions import BrowserSessionFetcher, launch_edge_cdp
from pyaireader.models import (
    BatchReadUrlsRequest,
    InspectUrlRequest,
    PlatformSearchRequest,
    ReadUrlRequest,
)
from pyaireader.reader import ReaderPipeline


def main() -> None:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(prog="pyaireader")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("url")
    read_parser.add_argument("--fetch-strategy", default="auto")
    read_parser.add_argument("--auth-strategy", default="user_session_fallback")
    read_parser.add_argument("--bypass-cache", action="store_true")
    read_parser.add_argument("--max-total-chars", type=int, default=16000)
    read_parser.add_argument("--max-clean-text-chars", type=int, default=12000)
    read_parser.add_argument("--save", action="store_true")
    read_parser.add_argument("--save-to", default="default")
    read_parser.add_argument("--project", default=None)
    read_parser.add_argument("--tag", action="append", default=[])
    read_parser.add_argument("--pretty", action="store_true")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("url")
    inspect_parser.add_argument("--fetch-strategy", default="auto")
    inspect_parser.add_argument("--auth-strategy", default="anonymous")
    inspect_parser.add_argument("--html-preview-chars", type=int, default=2000)
    inspect_parser.add_argument("--pretty", action="store_true")

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("file")
    batch_parser.add_argument("--fetch-strategy", default="auto")
    batch_parser.add_argument("--auth-strategy", default="user_session_fallback")
    batch_parser.add_argument("--bypass-cache", action="store_true")
    batch_parser.add_argument("--jsonl", action="store_true")

    search_parser = subparsers.add_parser("search-platform")
    search_parser.add_argument("platform", choices=["x"])
    search_parser.add_argument("query")
    search_parser.add_argument("--auth-strategy", default="user_session_fallback")
    search_parser.add_argument("--max-results", type=int, default=30)
    search_parser.add_argument("--max-pages", type=int, default=2)
    search_parser.add_argument("--time-range", default="latest", choices=["latest", "24h", "7d", "30d"])
    search_parser.add_argument(
        "--follow-links",
        default="same_platform",
        choices=["none", "same_platform", "same_platform_and_article_links"],
    )
    search_parser.add_argument("--pretty", action="store_true")

    browser_status_parser = subparsers.add_parser("browser-status")
    browser_status_parser.add_argument(
        "--provider",
        default=None,
        choices=["auto", "cdp", "persistent_profile"],
    )
    browser_status_parser.add_argument("--pretty", action="store_true")

    browser_login_parser = subparsers.add_parser("browser-login")
    browser_login_parser.add_argument("platform", choices=["x"])
    browser_login_parser.add_argument(
        "--provider",
        default="persistent_profile",
        choices=["persistent_profile"],
    )
    browser_login_parser.add_argument("--pretty", action="store_true")

    edge_cdp_parser = subparsers.add_parser("edge-cdp-launch")
    edge_cdp_parser.add_argument("--port", type=int, default=9222)
    edge_cdp_parser.add_argument("--url", default="about:blank")
    edge_cdp_parser.add_argument("--edge-path", default=None)
    edge_cdp_parser.add_argument("--user-data-dir", default=None)
    edge_cdp_parser.add_argument("--wait-seconds", type=float, default=4.0)
    edge_cdp_parser.add_argument("--pretty", action="store_true")

    clear_parser = subparsers.add_parser("clear-cache")
    clear_parser.add_argument("--url", default=None)
    clear_parser.add_argument("--domain", default=None)

    storage_status_parser = subparsers.add_parser("storage-status")
    storage_status_parser.add_argument("--pretty", action="store_true")

    library_parser = subparsers.add_parser("library")
    library_subparsers = library_parser.add_subparsers(dest="library_command", required=True)

    library_list_parser = library_subparsers.add_parser("list")
    library_list_parser.add_argument("--store", default="default")
    library_list_parser.add_argument("--limit", type=int, default=20)
    library_list_parser.add_argument("--offset", type=int, default=0)
    library_list_parser.add_argument("--project", default=None)
    library_list_parser.add_argument("--include-text", action="store_true")
    library_list_parser.add_argument("--pretty", action="store_true")

    library_get_parser = library_subparsers.add_parser("get")
    library_get_parser.add_argument("item_id")
    library_get_parser.add_argument("--store", default="default")
    library_get_parser.add_argument("--pretty", action="store_true")

    library_search_parser = library_subparsers.add_parser("search")
    library_search_parser.add_argument("query")
    library_search_parser.add_argument("--store", default="default")
    library_search_parser.add_argument("--limit", type=int, default=20)
    library_search_parser.add_argument("--project", default=None)
    library_search_parser.add_argument("--include-text", action="store_true")
    library_search_parser.add_argument("--pretty", action="store_true")

    library_export_parser = library_subparsers.add_parser("export")
    library_export_parser.add_argument("item_id")
    library_export_parser.add_argument("--store", default="default")
    library_export_parser.add_argument("--format", default="json", choices=["json", "md", "markdown"])
    library_export_parser.add_argument("--pretty", action="store_true")

    args = parser.parse_args()
    if args.command == "browser-status":
        result = BrowserSessionFetcher(provider_mode=args.provider).status()
        _print_json(result, pretty=args.pretty)
        return

    if args.command == "browser-login":
        result = BrowserSessionFetcher(provider_mode=args.provider).open_login(args.platform)
        _print_json(result, pretty=args.pretty)
        return

    if args.command == "edge-cdp-launch":
        result = launch_edge_cdp(
            port=args.port,
            url=args.url,
            edge_path=args.edge_path,
            user_data_dir=args.user_data_dir,
            wait_seconds=args.wait_seconds,
        )
        _print_json(result, pretty=args.pretty)
        return

    pipeline = ReaderPipeline.from_env()

    if args.command == "read":
        result = pipeline.read(
            ReadUrlRequest(
                url=args.url,
                fetch_strategy=args.fetch_strategy,
                auth_strategy=args.auth_strategy,
                bypass_cache=args.bypass_cache,
                max_total_chars=args.max_total_chars,
                max_clean_text_chars=args.max_clean_text_chars,
                save=args.save,
                save_to=args.save_to,
                project=args.project,
                tags=args.tag,
            )
        ).to_dict()
        _print_json(result, pretty=args.pretty)
        return

    if args.command == "inspect":
        result = pipeline.inspect(
            InspectUrlRequest(
                url=args.url,
                fetch_strategy=args.fetch_strategy,
                auth_strategy=args.auth_strategy,
                html_preview_chars=args.html_preview_chars,
            )
        )
        _print_json(result, pretty=args.pretty)
        return

    if args.command == "batch":
        with open(args.file, encoding="utf-8") as handle:
            urls = [line.strip() for line in handle if line.strip()]
        result = pipeline.batch_read(
            BatchReadUrlsRequest(
                urls=urls,
                fetch_strategy=args.fetch_strategy,
                auth_strategy=args.auth_strategy,
                bypass_cache=args.bypass_cache,
            )
        )
        if args.jsonl:
            for item in result["results"]:
                print(json.dumps(item, ensure_ascii=False))
        else:
            _print_json(result, pretty=True)
        return

    if args.command == "search-platform":
        result = pipeline.search_platform(
            PlatformSearchRequest(
                platform=args.platform,
                query=args.query,
                auth_strategy=args.auth_strategy,
                max_results=args.max_results,
                max_pages=args.max_pages,
                time_range=args.time_range,
                follow_links=args.follow_links,
            )
        ).to_dict()
        _print_json(result, pretty=args.pretty)
        return

    if args.command == "clear-cache":
        result = pipeline.clear_cache(url=args.url, domain=args.domain)
        _print_json(result, pretty=True)
        return

    if args.command == "storage-status":
        _print_json(pipeline.storage_status(), pretty=args.pretty)
        return

    if args.command == "library":
        if args.library_command == "list":
            result = pipeline.library_list(
                store=args.store,
                limit=args.limit,
                offset=args.offset,
                project=args.project,
                include_text=args.include_text,
            )
        elif args.library_command == "get":
            result = pipeline.library_get(args.item_id, store=args.store)
        elif args.library_command == "search":
            result = pipeline.library_search(
                args.query,
                store=args.store,
                limit=args.limit,
                project=args.project,
                include_text=args.include_text,
            )
        elif args.library_command == "export":
            result = pipeline.library_export(
                args.item_id,
                store=args.store,
                format=args.format,
            )
        else:
            raise ValueError(f"unknown library command: {args.library_command}")
        _print_json(result, pretty=args.pretty)
        return


def _print_json(data: dict, *, pretty: bool) -> None:
    indent = 2 if pretty else None
    print(json.dumps(data, ensure_ascii=False, indent=indent))


def _ensure_utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    if encoding != "utf-8":
        reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    main()
