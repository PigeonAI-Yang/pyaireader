from __future__ import annotations

import os
import time
from pathlib import Path

from pyaireader.browser_sessions.base import (
    BrowserProviderMode,
    BrowserReadOptions,
    BrowserSessionNotAvailable,
    BrowserSessionProvider,
)
from pyaireader.browser_sessions.cdp_provider import CDPBrowserSessionProvider, discover_cdp_endpoint
from pyaireader.browser_sessions.persistent_profile_provider import (
    PersistentProfileBrowserSessionProvider,
)
from pyaireader.fetchers import FetchResponse


class BrowserSessionFetcher:
    name = "authenticated_browser"

    def __init__(
        self,
        providers: list[BrowserSessionProvider] | None = None,
        timeout_ms: int = 30_000,
        provider_mode: BrowserProviderMode | str | None = None,
        cdp_endpoint: str | None = None,
        profile_dir: Path | str | None = None,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.provider_mode = _normalize_provider_mode(provider_mode)
        configured_cdp_endpoint = cdp_endpoint or os.getenv("PYAIREADER_BROWSER_CDP")
        self.cdp_endpoint = (
            discover_cdp_endpoint(configured_cdp_endpoint)
            if self.provider_mode in {"auto", "cdp"}
            else configured_cdp_endpoint
        )
        self.profile_dir = Path(
            profile_dir or os.getenv("PYAIREADER_BROWSER_PROFILE_DIR", _default_profile_dir())
        )
        self.providers = (
            providers
            if providers is not None
            else _default_providers(
                self.provider_mode,
                cdp_endpoint=self.cdp_endpoint,
                profile_dir=self.profile_dir,
            )
        )
        self.last_provider_name: str | None = None

    def available(self) -> bool:
        return any(provider.is_available() for provider in self.providers)

    def fetch(self, url: str, *, task_scope: str | None = None) -> FetchResponse:
        errors: list[str] = []
        options = BrowserReadOptions(timeout_ms=self.timeout_ms, task_scope=task_scope)
        start = time.perf_counter()
        for provider in self.providers:
            if not provider.is_available():
                continue
            try:
                snapshot = provider.open_page(url, options)
                self.last_provider_name = snapshot.provider
                text = snapshot.html or ""
                headers = {
                    "content-type": "text/html; charset=utf-8",
                    "x-pyaireader-engine": self.name,
                    "x-pyaireader-browser-provider": snapshot.provider,
                    "x-pyaireader-visible-text-length": str(len(snapshot.visible_text or "")),
                }
                if snapshot.title:
                    headers["x-pyaireader-title"] = snapshot.title
                raw = text.encode("utf-8", errors="ignore")
                return FetchResponse(
                    url=snapshot.url,
                    final_url=snapshot.final_url,
                    status_code=200,
                    content_type=headers["content-type"],
                    text=text,
                    raw=raw,
                    elapsed_ms=int((time.perf_counter() - start) * 1000),
                    visible_text=snapshot.visible_text or "",
                    headers=headers,
                    html_length=len(text),
                    text_length=len(snapshot.visible_text or ""),
                )
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")
        raise BrowserSessionNotAvailable("; ".join(errors) or "browser_session_not_available")

    def status(self) -> dict[str, object]:
        provider_statuses = [provider.status() for provider in self.providers]
        active_provider = next(
            (status.name for status in provider_statuses if status.available),
            None,
        )
        return {
            "success": True,
            "provider_mode": self.provider_mode,
            "active_provider": active_provider,
            "available": active_provider is not None,
            "cdp_endpoint": self.cdp_endpoint,
            "profile_dir": str(self.profile_dir),
            "providers": [status.to_dict() for status in provider_statuses],
            "note": _status_note(self.provider_mode, active_provider, self.cdp_endpoint),
        }

    def open_login(self, platform: str) -> dict[str, object]:
        login_url = _login_url(platform)
        provider = PersistentProfileBrowserSessionProvider(self.profile_dir)
        provider.open_interactive_login(login_url)
        return {
            "success": True,
            "platform": platform,
            "provider": provider.name,
            "profile_dir": str(self.profile_dir),
            "login_url": login_url,
        }


def _default_providers(
    provider_mode: BrowserProviderMode,
    *,
    cdp_endpoint: str | None,
    profile_dir: Path,
) -> list[BrowserSessionProvider]:
    providers: list[BrowserSessionProvider] = []
    if provider_mode in {"auto", "cdp"} and not cdp_endpoint:
        cdp_endpoint = discover_cdp_endpoint()
    if provider_mode in {"auto", "cdp"}:
        providers.append(CDPBrowserSessionProvider(cdp_endpoint))
    if provider_mode == "persistent_profile":
        providers.append(PersistentProfileBrowserSessionProvider(profile_dir))
    return providers


def _default_profile_dir() -> str:
    return str(Path.home() / ".pyaireader" / "browser-profiles" / "default")


def _normalize_provider_mode(value: BrowserProviderMode | str | None) -> BrowserProviderMode:
    mode = value or os.getenv("PYAIREADER_BROWSER_PROVIDER", "auto")
    if mode not in {"auto", "cdp", "persistent_profile"}:
        raise ValueError("browser provider must be one of: auto, cdp, persistent_profile")
    return mode  # type: ignore[return-value]


def _status_note(
    provider_mode: BrowserProviderMode,
    active_provider: str | None,
    cdp_endpoint: str | None,
) -> str:
    if active_provider == "cdp":
        return "connected_to_user_started_cdp_browser"
    if active_provider == "persistent_profile":
        return "using_pyaireader_persistent_profile"
    if provider_mode == "cdp":
        return "cdp_requested_but_not_available"
    if provider_mode == "auto":
        return (
            "no_user_started_cdp_browser_available; start Edge/Chrome with remote debugging "
            "or explicitly choose persistent_profile"
        )
    return "no_browser_session_provider_available"


def _login_url(platform: str) -> str:
    if platform == "x":
        return "https://x.com/home"
    raise ValueError("platform must be one of: x")
