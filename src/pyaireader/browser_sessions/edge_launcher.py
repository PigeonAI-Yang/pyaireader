from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen


DEFAULT_EDGE_PATHS = [
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
]


def launch_edge_cdp(
    *,
    port: int = 9222,
    url: str = "about:blank",
    edge_path: str | Path | None = None,
    user_data_dir: str | Path | None = None,
    wait_seconds: float = 4.0,
) -> dict[str, object]:
    if port <= 0 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    executable = Path(edge_path) if edge_path else _find_edge_executable()
    if executable is None or not executable.exists():
        return _result(
            success=False,
            port=port,
            endpoint=_endpoint(port),
            edge_path=None,
            user_data_dir=user_data_dir,
            process_id=None,
            message="edge_executable_not_found",
        )

    args = [
        str(executable),
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        url,
    ]
    if user_data_dir:
        args.insert(1, f"--user-data-dir={Path(user_data_dir)}")

    try:
        process = subprocess.Popen(  # noqa: S603
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        return _result(
            success=False,
            port=port,
            endpoint=_endpoint(port),
            edge_path=executable,
            user_data_dir=user_data_dir,
            process_id=None,
            message=f"edge_launch_failed: {exc}",
        )
    reachable = _wait_until_reachable(port, wait_seconds=wait_seconds)
    message = (
        "edge_cdp_available"
        if reachable
        else "edge_started_but_cdp_not_reachable; close normal Edge windows and launch again, or use persistent_profile"
    )
    return _result(
        success=reachable,
        port=port,
        endpoint=_endpoint(port),
        edge_path=executable,
        user_data_dir=user_data_dir,
        process_id=process.pid,
        message=message,
    )


def _find_edge_executable() -> Path | None:
    for path in DEFAULT_EDGE_PATHS:
        if path and path.exists():
            return path
    return None


def _wait_until_reachable(port: int, *, wait_seconds: float) -> bool:
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if _endpoint_reachable(port):
            return True
        time.sleep(0.2)
    return _endpoint_reachable(port)


def _endpoint_reachable(port: int) -> bool:
    try:
        with urlopen(_endpoint(port) + "/json/version", timeout=1):
            return True
    except Exception:
        return False


def _endpoint(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def _result(
    *,
    success: bool,
    port: int,
    endpoint: str,
    edge_path: Path | None,
    user_data_dir: str | Path | None,
    process_id: int | None,
    message: str,
) -> dict[str, object]:
    return {
        "success": success,
        "browser": "edge",
        "provider": "cdp",
        "port": port,
        "endpoint": endpoint,
        "edge_path": str(edge_path) if edge_path else None,
        "user_data_dir": str(user_data_dir) if user_data_dir else None,
        "process_id": process_id,
        "message": message,
        "env": {
            "PYAIREADER_BROWSER_PROVIDER": "cdp",
            "PYAIREADER_BROWSER_CDP": endpoint,
        },
        "powershell": [
            "$env:PYAIREADER_BROWSER_PROVIDER='cdp'",
            f"$env:PYAIREADER_BROWSER_CDP='{endpoint}'",
            "uv run pyaireader browser-status --pretty",
        ],
    }
