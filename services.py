"""Service-specific selectors for the supported meeting providers."""

from dataclasses import dataclass
from urllib.parse import urlsplit

Locator = tuple[str, str]


def detect_service(url: str) -> str | None:
    """Identify supported providers by URL hostname, without network requests."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".")
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if host in ("telemost.yandex.ru", "telemost.yandex.com"):
        return "telemost"
    if host == "ktalk.ru" or host.endswith(".ktalk.ru"):
        return "ktalk"
    return None


@dataclass(frozen=True)
class Service:
    label: str
    name_inputs: tuple[Locator, ...]
    join_buttons: tuple[Locator, ...]
    continue_buttons: tuple[Locator, ...] = ()
    warning_buttons: tuple[Locator, ...] = ()


# Prefer kTalk's stable test IDs and retain text fallbacks for installations
# that expose the same anonymous entry form without those attributes.
KTALK_NAME_INPUTS: tuple[Locator, ...] = (
    (
        "css selector",
        "[data-testid='AnonymousAuthorization.Input'] input[type='text']",
    ),
    ("css selector", "input[placeholder*='Сергей Иванов']"),
    ("css selector", "input[autocomplete='name']"),
)
KTALK_JOIN_BUTTONS: tuple[Locator, ...] = (
    (
        "css selector",
        "[data-testid='AnonymousAuthorization.Anonymous'] button",
    ),
    (
        "xpath",
        "//button[normalize-space(.)='Продолжить' or normalize-space(.)='Continue']",
    ),
)


# Preserve matching of both English and Russian Telemost UI labels.
CONTINUE_BUTTONS: tuple[Locator, ...] = (
    ("css selector", "button[class*='continueInBrowserButton_']"),
    (
        "xpath",
        "//button[contains(normalize-space(.), 'Продолжить в браузере') "
        "or contains(normalize-space(.), 'Continue in browser')]",
    ),
)
TELEMOST_NAME_INPUTS: tuple[Locator, ...] = (
    ("css selector", "input[data-testid='orb-textinput-input']"),
    ("css selector", "input[autocomplete='name']"),
)
TELEMOST_JOIN_BUTTONS: tuple[Locator, ...] = (
    ("css selector", "button[data-testid='enter-conference-button']"),
    (
        "xpath",
        "//button[contains(normalize-space(.), 'Подключиться') "
        "or normalize-space(.)='Продолжить' "
        "or contains(normalize-space(.), 'Join')]",
    ),
)
MEDIA_WARNING_BUTTONS: tuple[Locator, ...] = (
    (
        "xpath",
        "//button[contains(., 'Понятно') "
        "or contains(., 'Got it') "
        "or normalize-space(.)='OK']",
    ),
)


SERVICES = {
    "telemost": Service(
        "Yandex Telemost",
        TELEMOST_NAME_INPUTS,
        TELEMOST_JOIN_BUTTONS,
        CONTINUE_BUTTONS,
        MEDIA_WARNING_BUTTONS,
    ),
    "ktalk": Service("Kontur.Talk", KTALK_NAME_INPUTS, KTALK_JOIN_BUTTONS),
}
