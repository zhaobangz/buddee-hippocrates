"""SSRF-resistant outbound URL validation."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


class OutboundURLBlocked(ValueError):
    """Raised when an outbound destination is not permitted."""


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT", "production").strip().lower() == "production"


def _is_test_mode() -> bool:
    return os.getenv("BUDDI_TEST_MODE", "").strip() == "1" or os.getenv("ENVIRONMENT") == "test"


def _normalise_allowed_hosts(allowed_hosts: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None) -> set[str]:
    return {h.strip().lower().rstrip(".") for h in (allowed_hosts or []) if h and h.strip()}


def _host_is_allowed(host: str, allowed_hosts: set[str]) -> bool:
    if not allowed_hosts:
        return True
    host = host.lower().rstrip(".")
    for allowed in allowed_hosts:
        if allowed.startswith("*.") and host.endswith(allowed[1:]):
            return True
        if host == allowed:
            return True
    return False


def _validate_ip(ip: ipaddress._BaseAddress, *, allow_private_hosts: bool) -> None:
    if allow_private_hosts and not _is_production():
        return
    if not ip.is_global:
        raise OutboundURLBlocked(f"Outbound URL resolves to non-public address {ip}")


def _blocked_hostname(host: str, *, allow_private_hosts: bool) -> bool:
    if allow_private_hosts and not _is_production():
        return False
    return host in {"localhost", "metadata.google.internal"} or host.endswith(".localhost")


def _resolve_host(host: str) -> list[ipaddress._BaseAddress]:
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    addresses: list[ipaddress._BaseAddress] = []
    for info in infos:
        sockaddr = info[4]
        raw = sockaddr[0]
        addresses.append(ipaddress.ip_address(raw))
    return addresses


def validate_outbound_url(
    url: str,
    *,
    allowed_hosts: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    require_https: bool | None = None,
    allow_private_hosts: bool = False,
) -> str:
    """Validate and return ``url`` for safe outbound HTTP use.

    The validator rejects credentials, fragments, non-HTTP schemes, private or
    otherwise non-global IPs, and DNS answers that resolve to non-public ranges.
    In production, HTTPS is required unless ``require_https=False`` is passed
    explicitly for a controlled internal-only use case.
    """

    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise OutboundURLBlocked("Outbound URL must use http or https")
    https_required = _is_production() if require_https is None else require_https
    if https_required and parsed.scheme != "https":
        raise OutboundURLBlocked("Outbound URL must use https")
    if parsed.username or parsed.password:
        raise OutboundURLBlocked("Outbound URL must not contain credentials")
    if parsed.fragment:
        raise OutboundURLBlocked("Outbound URL must not contain a fragment")
    if not parsed.hostname:
        raise OutboundURLBlocked("Outbound URL must include a hostname")

    host = parsed.hostname.lower().rstrip(".")
    if _blocked_hostname(host, allow_private_hosts=allow_private_hosts):
        raise OutboundURLBlocked(f"Outbound URL host '{host}' is not permitted")
    normalised_allowed = _normalise_allowed_hosts(allowed_hosts)
    if not _host_is_allowed(host, normalised_allowed):
        raise OutboundURLBlocked(f"Outbound URL host '{host}' is not allowlisted")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            addresses = _resolve_host(host)
        except socket.gaierror as exc:
            if _is_test_mode():
                return url
            raise OutboundURLBlocked(f"Outbound URL hostname '{host}' could not be resolved") from exc
        if not addresses:
            raise OutboundURLBlocked(f"Outbound URL hostname '{host}' resolved to no addresses")
        for address in addresses:
            _validate_ip(address, allow_private_hosts=allow_private_hosts)
    else:
        _validate_ip(ip, allow_private_hosts=allow_private_hosts)
    return url


__all__ = ["OutboundURLBlocked", "validate_outbound_url"]
