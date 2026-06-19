from __future__ import annotations

import pytest

from pyaireader.errors import UnsafeUrlError
from pyaireader.reader.normalizer import normalize_url


def test_normalize_adds_https_scheme() -> None:
    assert normalize_url("example.com/path") == "https://example.com/path"


def test_normalize_rejects_file_scheme() -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_url("file:///C:/secret.txt")


def test_normalize_rejects_localhost() -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_url("http://localhost:8000")
