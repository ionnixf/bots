"""Kontur.Talk provider definition."""

from .base import Service

KTALK = Service(
    key="ktalk",
    label="Kontur.Talk",
    hosts=("ktalk.ru", "*.ktalk.ru"),
    # Prefer stable test IDs and keep text fallbacks for installations that
    # expose the anonymous entry form without those attributes.
    name_inputs=(
        (
            "css selector",
            "[data-testid='AnonymousAuthorization.Input'] input[type='text']",
        ),
        ("css selector", "input[placeholder*='Сергей Иванов']"),
        ("css selector", "input[autocomplete='name']"),
    ),
    join_buttons=(
        ("css selector", "[data-testid='AnonymousAuthorization.Anonymous'] button"),
        (
            "xpath",
            (
                "//button[normalize-space(.)='Продолжить' "
                "or normalize-space(.)='Continue']"
            ),
        ),
    ),
)
