from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


def run_sync_browser_operation(operation: Callable[[], T]) -> T:
    """Run sync Playwright code safely when an MCP host already owns an asyncio loop."""
    if not _has_running_event_loop():
        return operation()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyaireader-browser") as executor:
        return executor.submit(operation).result()


def _has_running_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True
