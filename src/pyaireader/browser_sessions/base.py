from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


BrowserProviderMode = Literal["auto", "cdp", "edge_cdp_profile", "persistent_profile"]


class BrowserSessionError(Exception):
    """Base error for user-authorized browser session reads."""


class BrowserSessionNotAvailable(BrowserSessionError):
    """No user browser session provider can currently read the page."""


@dataclass(frozen=True)
class BrowserReadOptions:
    timeout_ms: int = 30_000
    wait_for_selector: str | None = None
    task_scope: str | None = None


@dataclass
class BrowserPageSnapshot:
    url: str
    final_url: str
    title: str | None
    visible_text: str
    html: str
    captured_at: str
    provider: str
    user_session_used: bool = True


@dataclass(frozen=True)
class BrowserProviderStatus:
    name: str
    available: bool
    details: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "available": self.available,
            "details": self.details,
        }


class BrowserSessionProvider(Protocol):
    name: str

    def is_available(self) -> bool:
        ...

    def open_page(self, url: str, options: BrowserReadOptions) -> BrowserPageSnapshot:
        ...

    def status(self) -> BrowserProviderStatus:
        ...
