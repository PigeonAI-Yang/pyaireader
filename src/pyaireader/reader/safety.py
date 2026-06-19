from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from pyaireader.errors import UnsafeUrlError
from pyaireader.reader.normalizer import normalize_url


METADATA_IP = ipaddress.ip_address("169.254.169.254")


@dataclass(frozen=True)
class UrlSafetyResult:
    url: str
    hostname: str
    resolved_ips: list[str] = field(default_factory=list)


def assert_url_safe(url: str, *, resolve_dns: bool = True) -> UrlSafetyResult:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL must include a hostname")
    if hostname in {"localhost", "localhost.localdomain"}:
        raise UnsafeUrlError("Localhost URLs are not allowed")

    resolved_ips = _resolve_host(hostname) if resolve_dns else []
    if not resolved_ips:
        try:
            resolved_ips = [ipaddress.ip_address(hostname)]
        except ValueError:
            resolved_ips = []

    for ip in resolved_ips:
        if _is_blocked_ip(ip):
            raise UnsafeUrlError(f"URL host resolves to blocked IP: {ip}")

    return UrlSafetyResult(
        url=normalized,
        hostname=hostname,
        resolved_ips=[str(ip) for ip in resolved_ips],
    )


def _resolve_host(hostname: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"DNS resolve failed for host: {hostname}") from exc

    ips: list[ipaddress._BaseAddress] = []
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip not in ips:
            ips.append(ip)
    return ips


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip == METADATA_IP
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
