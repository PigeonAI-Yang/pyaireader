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
from pyaireader.browser_sessions.cdp_provider import (
    CDPBrowserSessionProvider,
    DEFAULT_EDGE_CDP_PROFILE_ENDPOINT,
    discover_cdp_endpoint,
)
from pyaireader.browser_sessions.edge_launcher import (
    DEFAULT_EDGE_CDP_PROFILE_PORT,
    default_edge_cdp_profile_dir,
    launch_edge_cdp_profile,
)
from pyaireader.browser_sessions.persistent_profile_provider import (
    PersistentProfileBrowserSessionProvider,
)
from pyaireader.browser_sessions.session_diagnostics import platform_session_status
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
        if self.provider_mode == "edge_cdp_profile":
            self.cdp_endpoint = (
                cdp_endpoint
                or os.getenv("PYAIREADER_EDGE_CDP_PROFILE_ENDPOINT")
                or DEFAULT_EDGE_CDP_PROFILE_ENDPOINT
            )
        elif self.provider_mode == "auto":
            discovered_cdp_endpoint = discover_cdp_endpoint(
                cdp_endpoint,
                dedicated_first=cdp_endpoint is None,
            )
            self.cdp_endpoint = discovered_cdp_endpoint or (
                DEFAULT_EDGE_CDP_PROFILE_ENDPOINT if cdp_endpoint is None else cdp_endpoint
            )
        elif self.provider_mode == "cdp":
            configured_cdp_endpoint = cdp_endpoint or os.getenv("PYAIREADER_BROWSER_CDP")
            self.cdp_endpoint = discover_cdp_endpoint(configured_cdp_endpoint)
        else:
            self.cdp_endpoint = cdp_endpoint or os.getenv("PYAIREADER_BROWSER_CDP")
        self.profile_dir = Path(
            profile_dir
            or os.getenv("PYAIREADER_BROWSER_PROFILE_DIR")
            or _default_profile_dir(self.provider_mode)
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
            "platform_sessions": _platform_sessions_for_status(
                self.provider_mode,
                self.profile_dir,
            ),
            "providers": [status.to_dict() for status in provider_statuses],
            "note": _status_note(self.provider_mode, active_provider, self.cdp_endpoint),
        }

    def open_login(self, platform: str) -> dict[str, object]:
        login_url = _login_url(platform)
        if self.provider_mode == "edge_cdp_profile":
            launch_result = launch_edge_cdp_profile(
                url=login_url,
                profile_dir=self.profile_dir,
                port=_port_from_endpoint(self.cdp_endpoint),
            )
            return {
                "success": launch_result["success"],
                "platform": platform,
                "provider": "edge_cdp_profile",
                "profile_dir": str(self.profile_dir),
                "login_url": login_url,
                "endpoint": self.cdp_endpoint,
                "launch": launch_result,
                "session_status": platform_session_status(self.profile_dir).get(platform),
            }
        provider = PersistentProfileBrowserSessionProvider(self.profile_dir)
        provider.open_interactive_login(login_url)
        provider_status = provider.status().details
        platform_sessions = provider_status.get("platform_sessions", {})
        session_status = (
            platform_sessions.get(platform)
            if isinstance(platform_sessions, dict)
            else None
        )
        return {
            "success": True,
            "platform": platform,
            "provider": provider.name,
            "profile_dir": str(self.profile_dir),
            "login_url": login_url,
            "session_status": session_status,
        }


def _default_providers(
    provider_mode: BrowserProviderMode,
    *,
    cdp_endpoint: str | None,
    profile_dir: Path,
) -> list[BrowserSessionProvider]:
    providers: list[BrowserSessionProvider] = []
    if provider_mode == "auto":
        providers.append(
            CDPBrowserSessionProvider(
                cdp_endpoint,
                name="edge_cdp_profile",
                use_env_endpoint=False,
            )
        )
    if provider_mode == "cdp":
        providers.append(CDPBrowserSessionProvider(cdp_endpoint))
    if provider_mode == "edge_cdp_profile":
        providers.append(CDPBrowserSessionProvider(cdp_endpoint, name="edge_cdp_profile"))
    if provider_mode == "persistent_profile":
        providers.append(PersistentProfileBrowserSessionProvider(profile_dir))
    return providers


def _default_profile_dir(provider_mode: BrowserProviderMode) -> str:
    if provider_mode in {"auto", "edge_cdp_profile"}:
        return str(default_edge_cdp_profile_dir())
    return str(Path.home() / ".pyaireader" / "browser-profiles" / "default")


def _normalize_provider_mode(value: BrowserProviderMode | str | None) -> BrowserProviderMode:
    mode = value or os.getenv("PYAIREADER_BROWSER_PROVIDER", "auto")
    if mode not in {"auto", "cdp", "edge_cdp_profile", "persistent_profile"}:
        raise ValueError(
            "browser provider must be one of: auto, cdp, edge_cdp_profile, persistent_profile"
        )
    return mode  # type: ignore[return-value]


def _status_note(
    provider_mode: BrowserProviderMode,
    active_provider: str | None,
    cdp_endpoint: str | None,
) -> str:
    if active_provider == "edge_cdp_profile":
        return "connected_to_dedicated_edge_cdp_profile"
    if active_provider == "cdp":
        if cdp_endpoint == DEFAULT_EDGE_CDP_PROFILE_ENDPOINT:
            return "connected_to_dedicated_edge_cdp_profile"
        return "connected_to_user_started_cdp_browser"
    if active_provider == "persistent_profile":
        return "using_pyaireader_persistent_profile"
    if provider_mode == "cdp":
        return "cdp_requested_but_not_available"
    if provider_mode == "auto":
        return (
            "no_browser_cdp_available; run edge-cdp-profile-launch for logged-in sites "
            "or explicitly choose another provider"
        )
    if provider_mode == "edge_cdp_profile":
        return "dedicated_edge_cdp_profile_not_available; run edge-cdp-profile-launch"
    return "no_browser_session_provider_available"


def _login_url(platform: str) -> str:
    if platform == "x":
        return "https://x.com/home"
    raise ValueError("platform must be one of: x")


def _platform_sessions_for_status(
    provider_mode: BrowserProviderMode,
    profile_dir: Path,
) -> dict[str, object] | None:
    if provider_mode in {"auto", "edge_cdp_profile", "persistent_profile"}:
        return platform_session_status(profile_dir)
    return None


def _port_from_endpoint(endpoint: str | None) -> int:
    if not endpoint:
        return DEFAULT_EDGE_CDP_PROFILE_PORT
    try:
        return int(endpoint.rstrip("/").rsplit(":", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"invalid CDP endpoint: {endpoint}") from exc
