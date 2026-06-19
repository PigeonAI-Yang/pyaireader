from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pyaireader.models import BatchReadUrlsRequest, InspectUrlRequest, ReadUrlRequest
from pyaireader.reader import ReaderPipeline


def handle_api_request(path: str, payload: dict[str, Any], pipeline: ReaderPipeline) -> tuple[int, dict]:
    if path == "/health":
        return HTTPStatus.OK, {"success": True, "service": "pyaireader"}
    if path == "/v1/read":
        return HTTPStatus.OK, pipeline.read(ReadUrlRequest(**payload)).to_dict()
    if path == "/v1/batch-read":
        return HTTPStatus.OK, pipeline.batch_read(BatchReadUrlsRequest(**payload))
    if path == "/v1/inspect":
        return HTTPStatus.OK, pipeline.inspect(InspectUrlRequest(**payload))
    if path == "/v1/cache/clear":
        return HTTPStatus.OK, pipeline.clear_cache(
            url=payload.get("url"),
            domain=payload.get("domain"),
        )
    return HTTPStatus.NOT_FOUND, {
        "success": False,
        "error": {"code": "not_found", "message": f"unknown endpoint: {path}"},
    }


def make_handler(pipeline: ReaderPipeline):
    class PyaireaderHandler(BaseHTTPRequestHandler):
        server_version = "pyaireader/0.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._write_json(HTTPStatus.OK, {"success": True, "service": "pyaireader"})
                return
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"success": False, "error": {"code": "not_found", "message": self.path}},
            )

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8"))
                status, response = handle_api_request(self.path, payload, pipeline)
                self._write_json(status, response)
            except Exception as exc:
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "success": False,
                        "error": {
                            "code": exc.__class__.__name__.lower(),
                            "message": str(exc),
                        },
                    },
                )

        def log_message(self, format: str, *args) -> None:  # noqa: A002, ANN002
            return

        def _write_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return PyaireaderHandler


def main() -> None:
    parser = argparse.ArgumentParser(prog="pyaireader-api")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    pipeline = ReaderPipeline.from_env()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(pipeline))
    print(f"pyaireader-api listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
