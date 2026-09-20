"""Service-specific selectors for the supported meeting providers."""

from dataclasses import dataclass

Locator = tuple[str, str]


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
        "//button[contains(normalize-space(.), '\u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435') "
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
        "//button[contains(normalize-space(.), '\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f') "
        "or normalize-space(.)='\u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c' "
        "or contains(normalize-space(.), 'Join')]",
    ),
)
MEDIA_WARNING_BUTTONS: tuple[Locator, ...] = (
    (
        "xpath",
        "//button[contains(., '\u041f\u043e\u043d\u044f\u0442\u043d\u043e') "
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
