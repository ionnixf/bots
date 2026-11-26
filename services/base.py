"""Provider-neutral model shared by every supported meeting service.

A new service is added by describing its UI in one :class:`Service` instance and
registering it in ``services/__init__.py``. The launcher contains no
service-specific selectors, hosts, or meeting URLs.
"""

from __future__ import annotations

from dataclasses import dataclass

# A Playwright locator strategy and selector, e.g. ("css selector", "button").
Locator = tuple[str, str]


def matches_host(hostname: str, patterns: tuple[str, ...]) -> bool:
    """Match a hostname against exact names and ``*.`` suffix patterns."""
    host = hostname.lower().rstrip(".")
    for pattern in patterns:
        candidate = pattern.lower()
        if candidate.startswith("*."):
            suffix = candidate[1:]  # ".ktalk.ru"
            if host.endswith(suffix) and len(host) > len(suffix):
                return True
        elif host == candidate:
            return True
    return False


@dataclass(frozen=True)
class Service:
    """Everything the generic launcher needs to know about one provider.

    Only ``key``, ``label``, and ``hosts`` are required. Optional locators are
    tried in order, so specific selectors should come before text fallbacks.
    Markers are case-insensitive substrings of the rendered page text.
    """

    key: str
    label: str
    hosts: tuple[str, ...]
    # Guest name field and the button that submits the join form.
    name_inputs: tuple[Locator, ...] = ()
    join_buttons: tuple[Locator, ...] = ()
    # "Continue in browser" interstitials shown outside the meeting app.
    continue_buttons: tuple[Locator, ...] = ()
    # Modal dialogs (onboarding, missing-device warnings) blocking the form.
    overlay_buttons: tuple[Locator, ...] = ()
    # Controls that disable an already-enabled device before joining.
    mic_off_buttons: tuple[Locator, ...] = ()
    camera_off_buttons: tuple[Locator, ...] = ()
    # In-meeting/waiting-room controls and text that prove the join worked.
    joined_buttons: tuple[Locator, ...] = ()
    joined_markers: tuple[str, ...] = ()
    # Text proving the link is invalid, the meeting ended, or access was lost.
    failure_markers: tuple[str, ...] = ()
    # URLs of embedded guest frames that can be opened directly as a fallback.
    frame_url_patterns: tuple[str, ...] = ()
    # Query parameters forced on the direct fallback URL.
    direct_frame_params: tuple[tuple[str, str], ...] = ()

    def matches_host(self, hostname: str) -> bool:
        return matches_host(hostname, self.hosts)
