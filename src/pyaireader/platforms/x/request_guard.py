from __future__ import annotations

import json
import os
import random
import time
from contextlib import contextmanager
from pathlib import Path


class XRequestGuardBlocked(RuntimeError):
    pass


class XRequestGuard:
    """Cross-process pacing and cooldown for user-authorized X browser reads."""

    def __init__(self, state_dir: Path | None = None) -> None:
        self.state_dir = state_dir or Path.home() / ".pyaireader" / "guards"
        self.state_path = self.state_dir / "x-request-guard.json"
        self.lock_path = self.state_dir / "x-request-guard.lock"
        self.minimum_interval = _env_seconds("PYAIREADER_X_MIN_INTERVAL_SECONDS", 8.0)
        self.jitter = _env_seconds("PYAIREADER_X_JITTER_SECONDS", 7.0)
        self.max_per_hour = _env_int("PYAIREADER_X_MAX_REQUESTS_PER_HOUR", 300)
        self.base_backoff = _env_seconds("PYAIREADER_X_ERROR_BACKOFF_SECONDS", 60.0)
        self.max_backoff = _env_seconds("PYAIREADER_X_MAX_BACKOFF_SECONDS", 900.0)

    def wait(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._lock():
            state = self._read_state()
            now = time.time()
            if state["cooldown_until"] > now:
                seconds = int(state["cooldown_until"] - now) + 1
                raise XRequestGuardBlocked(f"x_safety_cooldown_active:{seconds}s")
            recent = [timestamp for timestamp in state["requests"] if timestamp > now - 3600]
            if len(recent) >= self.max_per_hour:
                seconds = int(min(recent) + 3600 - now) + 1
                raise XRequestGuardBlocked(f"x_hourly_request_budget_exhausted:{seconds}s")
            earliest = state["last_request_at"] + self.minimum_interval
            wait_seconds = max(0.0, earliest - now) + random.uniform(0.0, self.jitter)
            if wait_seconds:
                time.sleep(wait_seconds)
            request_at = time.time()
            state["last_request_at"] = request_at
            state["requests"] = [*recent, request_at]
            self._write_state(state)

    def record_success(self) -> None:
        with self._lock():
            state = self._read_state()
            state["consecutive_failures"] = 0
            state["cooldown_until"] = 0.0
            self._write_state(state)

    def record_failure(self, *, rate_limited: bool = False) -> None:
        with self._lock():
            state = self._read_state()
            failures = int(state["consecutive_failures"]) + 1
            multiplier = 4 if rate_limited else 1
            backoff = min(self.base_backoff * (2 ** (failures - 1)) * multiplier, self.max_backoff)
            state["consecutive_failures"] = failures
            state["cooldown_until"] = max(float(state["cooldown_until"]), time.time() + backoff)
            self._write_state(state)

    @contextmanager
    def _lock(self):
        deadline = time.monotonic() + 30.0
        self.state_dir.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.lock_path.mkdir()
                break
            except FileExistsError:
                if _is_stale(self.lock_path, older_than=60.0):
                    try:
                        self.lock_path.rmdir()
                    except OSError:
                        pass
                if time.monotonic() >= deadline:
                    raise XRequestGuardBlocked("x_request_guard_lock_timeout")
                time.sleep(0.1)
        try:
            yield
        finally:
            try:
                self.lock_path.rmdir()
            except OSError:
                pass

    def _read_state(self) -> dict[str, object]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            value = {}
        return {
            "last_request_at": float(value.get("last_request_at", 0.0)),
            "requests": [float(item) for item in value.get("requests", []) if isinstance(item, (int, float))],
            "consecutive_failures": int(value.get("consecutive_failures", 0)),
            "cooldown_until": float(value.get("cooldown_until", 0.0)),
        }

    def _write_state(self, state: dict[str, object]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(f"{json.dumps(state, sort_keys=True)}\n", encoding="utf-8")
        temporary.replace(self.state_path)


def _env_seconds(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(0.0, value)


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(1, value)


def _is_stale(path: Path, *, older_than: float) -> bool:
    try:
        return time.time() - path.stat().st_mtime > older_than
    except OSError:
        return False
