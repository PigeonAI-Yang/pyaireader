from pathlib import Path

import pytest

from pyaireader.platforms.x.request_guard import XRequestGuard, XRequestGuardBlocked


def test_x_request_guard_default_budget_covers_daily_collection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PYAIREADER_X_MAX_REQUESTS_PER_HOUR", raising=False)

    guard = XRequestGuard(tmp_path)

    assert guard.max_per_hour == 300


def test_x_request_guard_enforces_hourly_budget(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYAIREADER_X_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("PYAIREADER_X_JITTER_SECONDS", "0")
    monkeypatch.setenv("PYAIREADER_X_MAX_REQUESTS_PER_HOUR", "2")
    guard = XRequestGuard(tmp_path)

    guard.wait()
    guard.wait()

    with pytest.raises(XRequestGuardBlocked, match="hourly_request_budget"):
        guard.wait()


def test_x_request_guard_enters_cooldown_after_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYAIREADER_X_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("PYAIREADER_X_JITTER_SECONDS", "0")
    monkeypatch.setenv("PYAIREADER_X_ERROR_BACKOFF_SECONDS", "60")
    monkeypatch.setenv("PYAIREADER_X_MAX_BACKOFF_SECONDS", "900")
    guard = XRequestGuard(tmp_path)

    guard.record_failure(rate_limited=True)

    with pytest.raises(XRequestGuardBlocked, match="cooldown_active"):
        guard.wait()
