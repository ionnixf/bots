"""Yandex Telemost provider definition.

Since the Telemost/Messenger merge (2026) the guest join form is rendered in a
child frame such as ``https://telemost.yandex.ru/private-join/<ROOM>``. The
launcher searches every frame, so these locators are not scoped to one document.
"""

from .base import Service

TELEMOST = Service(
    key="telemost",
    label="Yandex Telemost",
    hosts=(
        "telemost.yandex.ru",
        "telemost.yandex.com",
        "telemost.360.yandex.ru",
    ),
    name_inputs=(
        ("css selector", "input[data-testid='orb-textinput-input']"),
        ("css selector", "input[autocomplete='name']"),
        ("css selector", "input[placeholder*='имя' i]"),
        ("css selector", "input[placeholder*='name' i]"),
    ),
    join_buttons=(
        ("css selector", "button[data-testid='enter-conference-button']"),
        (
            "xpath",
            (
                "//button[normalize-space(.)='Подключиться' "
                "or normalize-space(.)='Присоединиться' "
                "or normalize-space(.)='Продолжить' "
                "or normalize-space(.)='Join' "
                "or normalize-space(.)='Join meeting']"
            ),
        ),
    ),
    continue_buttons=(
        ("css selector", "button[data-testid='meeting-continue-in-browser-continue']"),
        (
            "xpath",
            (
                "//button[contains(normalize-space(.), 'Продолжить в браузере') "
                "or contains(normalize-space(.), 'Continue in browser')]"
            ),
        ),
    ),
    overlay_buttons=(
        ("css selector", "button[data-testid='telemost-3-onboarding-confirm']"),
        ("css selector", "button[data-testid='telemost-3-onboarding-close']"),
        (
            "xpath",
            (
                "//button[normalize-space(.)='Понятно' "
                "or normalize-space(.)='Got it' "
                "or normalize-space(.)='OK']"
            ),
        ),
    ),
    mic_off_buttons=(
        ("css selector", "button[data-testid='turn-off-mic-button']"),
        (
            "xpath",
            (
                "//button[contains(@aria-label, 'Выключить микрофон') "
                "or contains(@title, 'Выключить микрофон') "
                "or contains(@aria-label, 'Turn off microphone') "
                "or contains(@title, 'Turn off microphone')]"
            ),
        ),
    ),
    camera_off_buttons=(
        ("css selector", "button[data-testid='turn-off-camera-button']"),
        (
            "xpath",
            (
                "//button[contains(@aria-label, 'Выключить камеру') "
                "or contains(@title, 'Выключить камеру') "
                "or contains(@aria-label, 'Turn off camera') "
                "or contains(@title, 'Turn off camera')]"
            ),
        ),
    ),
    joined_buttons=(
        ("css selector", "button[data-testid='end-call-alt-button']"),
        ("css selector", "button[data-testid='participants-button']"),
    ),
    joined_markers=(
        "зал ожидания",
        "организатор скоро впустит",
        "ожидайте, пока организатор",
        "waiting for the host",
        "you're in the waiting room",
    ),
    failure_markers=(
        "такого звонка нет",
        "ссылка недействительна",
        "встреча не найдена",
        "встреча завершена",
        "звонок завершён",
        "звонок завершен",
        "вы были удалены",
        "call not found",
        "meeting not found",
        "invalid link",
        "meeting has ended",
        "call has ended",
        "you were removed",
    ),
    # Only the embedded guest frame is a valid direct fallback target.
    frame_url_patterns=(r"/private-join/",),
    direct_frame_params=(("mic", "off"), ("camera", "off")),
)
