from __future__ import annotations

import argparse
import json
import sys

from pyaireader.models import BatchReadUrlsRequest, InspectUrlRequest, ReadUrlRequest
from pyaireader.reader import ReaderPipeline


def main() -> None:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(prog="pyaireader")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("url")
    read_parser.add_argument("--fetch-strategy", default="auto")
    read_parser.add_argument("--bypass-cache", action="store_true")
    read_parser.add_argument("--max-total-chars", type=int, default=16000)
    read_parser.add_argument("--max-clean-text-chars", type=int, default=12000)
    read_parser.add_argument("--pretty", action="store_true")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("url")
    inspect_parser.add_argument("--fetch-strategy", default="auto")
    inspect_parser.add_argument("--html-preview-chars", type=int, default=2000)
    inspect_parser.add_argument("--pretty", action="store_true")

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("file")
    batch_parser.add_argument("--fetch-strategy", default="auto")
    batch_parser.add_argument("--bypass-cache", action="store_true")
    batch_parser.add_argument("--jsonl", action="store_true")

    clear_parser = subparsers.add_parser("clear-cache")
    clear_parser.add_argument("--url", default=None)
    clear_parser.add_argument("--domain", default=None)

    args = parser.parse_args()
    pipeline = ReaderPipeline.from_env()

    if args.command == "read":
        result = pipeline.read(
            ReadUrlRequest(
                url=args.url,
                fetch_strategy=args.fetch_strategy,
                bypass_cache=args.bypass_cache,
                max_total_chars=args.max_total_chars,
                max_clean_text_chars=args.max_clean_text_chars,
            )
        ).to_dict()
        _print_json(result, pretty=args.pretty)
        return

    if args.command == "inspect":
        result = pipeline.inspect(
            InspectUrlRequest(
                url=args.url,
                fetch_strategy=args.fetch_strategy,
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
                bypass_cache=args.bypass_cache,
            )
        )
        if args.jsonl:
            for item in result["results"]:
                print(json.dumps(item, ensure_ascii=False))
        else:
            _print_json(result, pretty=True)
        return

    if args.command == "clear-cache":
        result = pipeline.clear_cache(url=args.url, domain=args.domain)
        _print_json(result, pretty=True)
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
