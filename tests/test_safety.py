from __future__ import annotations

import socket

import pytest

from pyaireader.errors import UnsafeUrlError
from pyaireader.reader.normalizer import normalize_url
from pyaireader.reader.safety import assert_url_safe


def test_normalize_rejects_userinfo_url() -> None:
    with pytest.raises(UnsafeUrlError):
        normalize_url("https://user:pass@example.com/article")


def test_safety_rejects_metadata_ip() -> None:
    with pytest.raises(UnsafeUrlError):
        assert_url_safe("http://169.254.169.254/latest/meta-data/")


def test_safety_rejects_ipv6_loopback() -> None:
    with pytest.raises(UnsafeUrlError):
        assert_url_safe("http://[::1]/")


def test_safety_rejects_dns_private_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):  # noqa: ANN002, ANN003
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(UnsafeUrlError):
        assert_url_safe("https://example.com")
