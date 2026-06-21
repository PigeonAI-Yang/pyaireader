from __future__ import annotations

import sqlite3
from pathlib import Path


X_REQUIRED_AUTH_COOKIES = {"auth_token", "ct0"}


def platform_session_status(profile_dir: Path) -> dict[str, object]:
    return {
        "x": x_session_status(profile_dir),
    }


def x_session_status(profile_dir: Path) -> dict[str, object]:
    cookie_db = _first_existing_cookie_db(profile_dir)
    if cookie_db is None:
        return {
            "platform": "x",
            "logged_in": False,
            "cookie_db_exists": False,
            "required_cookie_names": sorted(X_REQUIRED_AUTH_COOKIES),
            "present_auth_cookie_names": [],
            "cookie_hosts": {},
            "message": "x_cookie_db_not_found",
        }

    try:
        cookie_names, cookie_hosts = _read_x_cookie_names(cookie_db)
    except sqlite3.Error as exc:
        return {
            "platform": "x",
            "logged_in": False,
            "cookie_db_exists": True,
            "cookie_db": str(cookie_db),
            "required_cookie_names": sorted(X_REQUIRED_AUTH_COOKIES),
            "present_auth_cookie_names": [],
            "cookie_hosts": {},
            "message": f"x_cookie_db_unreadable: {exc}",
        }

    present = sorted(X_REQUIRED_AUTH_COOKIES.intersection(cookie_names))
    logged_in = X_REQUIRED_AUTH_COOKIES.issubset(cookie_names)
    return {
        "platform": "x",
        "logged_in": logged_in,
        "cookie_db_exists": True,
        "cookie_db": str(cookie_db),
        "required_cookie_names": sorted(X_REQUIRED_AUTH_COOKIES),
        "present_auth_cookie_names": present,
        "cookie_hosts": cookie_hosts,
        "message": "x_logged_in" if logged_in else "x_auth_cookies_missing",
    }


def _first_existing_cookie_db(profile_dir: Path) -> Path | None:
    for path in [
        profile_dir / "Default" / "Network" / "Cookies",
        profile_dir / "Default" / "Cookies",
    ]:
        if path.exists():
            return path
    return None


def _read_x_cookie_names(cookie_db: Path) -> tuple[set[str], dict[str, int]]:
    connection = sqlite3.connect(f"file:{cookie_db}?mode=ro", uri=True, timeout=1.0)
    try:
        rows = connection.execute(
            """
            SELECT host_key, name
            FROM cookies
            WHERE host_key LIKE '%x.com%' OR host_key LIKE '%twitter.com%'
            """
        ).fetchall()
    finally:
        connection.close()

    cookie_names: set[str] = set()
    cookie_hosts: dict[str, int] = {}
    for host_key, name in rows:
        cookie_names.add(str(name))
        host = str(host_key)
        cookie_hosts[host] = cookie_hosts.get(host, 0) + 1
    return cookie_names, cookie_hosts
