"""Supported meeting services.

Adding a provider means creating ``services/<key>.py`` with one :class:`Service`
instance and adding it to :data:`SERVICES`. URL detection, the CLI, and the join
engine then work without further changes.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from .base import Locator, Service, matches_host
from .ktalk import KTALK
from .telemost import TELEMOST

SERVICES: dict[str, Service] = {service.key: service for service in (TELEMOST, KTALK)}

__all__ = [
    "SERVICES",
    "Locator",
    "Service",
    "detect_service",
    "get_service",
    "matches_host",
]


def detect_service(url: str) -> str | None:
    """Identify a supported provider by URL hostname, without network requests."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".")
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    for service in SERVICES.values():
        if service.matches_host(host):
            return service.key
    return None


def get_service(key: str) -> Service:
    """Return a registered provider or raise a helpful ``KeyError``."""
    try:
        return SERVICES[key]
    except KeyError:
        available = ", ".join(SERVICES)
        raise KeyError(
            f"unknown meeting service {key!r}; available: {available}"
        ) from None
