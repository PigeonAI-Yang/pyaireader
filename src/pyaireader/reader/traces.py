from __future__ import annotations

import hashlib


def sha256_text(value: str | bytes | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.encode("utf-8", errors="ignore")
    return "sha256:" + hashlib.sha256(value).hexdigest()
