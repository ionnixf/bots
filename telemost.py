#!/usr/bin/env python3
"""Async Telemost guests in isolated contexts of one Chromium browser."""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
import time
from pathlib import Path

DEFAULT_MEETING_URL = "https://telemost.yandex.ru/j/62028536298781"
DEFAULT_COUNT = 15
FIRST_NAMES = (
    "Alex",
    "Mary",
    "John",
    "Helen",
    "David",
    "Anna",
    "Sam",
    "Olivia",
    "Paul",
    "Taylor",
)
LAST_NAMES = (
    "Smith",
    "Brown",
    "Miller",
    "Wilson",
    "Moore",
    "Taylor",
    "Anderson",
    "Thomas",
)
# Keep Russian first names and surnames in matching grammatical genders.
RUSSIAN_NAME_GROUPS = (
    (
        (
            "\u0410\u043b\u0435\u043a\u0441\u0430\u043d\u0434\u0440",
            "\u0418\u0432\u0430\u043d",
            "\u0414\u043c\u0438\u0442\u0440\u0438\u0439",
            "\u0421\u0435\u0440\u0433\u0435\u0439",
            "\u041f\u0430\u0432\u0435\u043b",
        ),
        (
            "\u0418\u0432\u0430\u043d\u043e\u0432",
            "\u041f\u0435\u0442\u0440\u043e\u0432",
            "\u0421\u043c\u0438\u0440\u043d\u043e\u0432",
            "\u0421\u043e\u043a\u043e\u043b\u043e\u0432",
            "\u041c\u043e\u0440\u043e\u0437\u043e\u0432",
        ),
    ),
    (
        (
            "\u041c\u0430\u0440\u0438\u044f",
            "\u0415\u043b\u0435\u043d\u0430",
            "\u0410\u043d\u043d\u0430",
            "\u041e\u043b\u044c\u0433\u0430",
            "\u0422\u0430\u0442\u044c\u044f\u043d\u0430",
        ),
        (
            "\u0418\u0432\u0430\u043d\u043e\u0432\u0430",
            "\u041f\u0435\u0442\u0440\u043e\u0432\u0430",
            "\u0421\u043c\u0438\u0440\u043d\u043e\u0432\u0430",
            "\u0421\u043e\u043a\u043e\u043b\u043e\u0432\u0430",
            "\u041c\u043e\u0440\u043e\u0437\u043e\u0432\u0430",
        ),
    ),
)
Locator = tuple[str, str]


def log(message: str, index: int | None = None) -> None:
    guest = f" [Guest {index + 1}]" if index is not None else ""
    print(f"[{time.strftime('%H:%M:%S')}]{guest} {message}", flush=True)


def random_name(language: str = "en") -> str:
    if language == "ru":
        first_names, last_names = random.choice(RUSSIAN_NAME_GROUPS)
    elif language == "en":
        first_names, last_names = FIRST_NAMES, LAST_NAMES
    else:
        raise ValueError(f"Unsupported name language: {language}")
    return f"{random.choice(first_names)} {random.choice(last_names)}"


# Preserve matching of both English and Russian Telemost UI labels.
CONTINUE_BUTTONS: tuple[Locator, ...] = (
    ("css selector", "button[class*='continueInBrowserButton_']"),
    (
        "xpath",
        "//button[contains(normalize-space(.), '\u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435') "
        "or contains(normalize-space(.), 'Continue in browser')]",
    ),
)
NAME_INPUTS: tuple[Locator, ...] = (
    ("css selector", "input[data-testid='orb-textinput-input']"),
    ("css selector", "input[autocomplete='name']"),
)
JOIN_BUTTONS: tuple[Locator, ...] = (
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


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def non_negative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be finite and non-negative")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Join a Telemost meeting with isolated, concurrent Playwright guest sessions."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_MEETING_URL,
        help="meeting URL (defaults to the saved meeting)",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=positive_int,
        default=DEFAULT_COUNT,
        help="total guest sessions (default: 15)",
    )
    parser.add_argument(
        "--name-language",
        choices=("ru", "en"),
        default="en",
        help="language of generated guest names (default: en)",
    )
    parser.add_argument(
        "--workers",
        type=positive_int,
        default=3,
        help="concurrent join attempts (default: 3)",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=0.0,
        help="minimum interval between join attempts, in seconds (default: 0)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=30,
        help="browser launch and per-action timeout, in seconds (default: 30)",
    )
    parser.add_argument(
        "--chrome-binary", help="optional Chrome/Chromium executable path"
    )
    parser.add_argument(
        "--headed", action="store_true", help="show the browser for debugging"
    )
    parser.add_argument(
        "--load-images", action="store_true", help="load images (blocked by default)"
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="close all sessions after join attempts finish",
    )
    return parser.parse_args(argv)


def visible_locator(page, selectors):
    result = None
    for by, selector in selectors:
        locator = page.locator(f"xpath={selector}" if by == "xpath" else selector)
        result = locator if result is None else result.or_(locator)
    return result.filter(visible=True)


async def configure_context(context, load_images: bool) -> None:
    # On Chromium, grantPermissions denies every permission absent from this
    # list. An empty list explicitly denies camera/microphone before navigation.
    await context.grant_permissions([])
    if not load_images:

        async def route_request(route):
            if route.request.resource_type == "image":
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", route_request)


async def join_guest(browser, args, index, contexts) -> bool:
    context = None
    page = None
    joined = False
    stage = "context creation"
    started = time.monotonic()
    name = random_name(args.name_language)
    try:
        log(f"Creating isolated session: {name}...", index)
        context = await browser.new_context(
            viewport={"width": 960, "height": 720},
            service_workers="block",
        )
        contexts.append(context)
        context.set_default_timeout(args.timeout * 1000)
        await configure_context(context, args.load_images)
        page = await context.new_page()
        warnings = visible_locator(page, MEDIA_WARNING_BUTTONS).last

        async def dismiss_warning():
            log("Dismissing camera/microphone warning...", index)
            await warnings.click()

        await page.add_locator_handler(warnings, dismiss_warning, no_wait_after=True)
        stage = "page navigation"
        log("Opening the meeting page...", index)
        await page.goto(args.url, wait_until="domcontentloaded")

        stage = "waiting for the join form"
        name_input = visible_locator(page, NAME_INPUTS).first
        continuation = visible_locator(page, CONTINUE_BUTTONS).first
        log("Waiting for the join form or 'Continue in browser'...", index)
        await name_input.or_(continuation).first.wait_for()
        if not await name_input.is_visible():
            await continuation.click()
            log("Clicked 'Continue in browser'.", index)

        stage = "entering guest name"
        await name_input.fill(name)
        # Blur commits the field in applications that update state on change.
        await name_input.press("Tab")
        log(f"Entered name: {name}.", index)
        stage = "joining"
        log("Clicking the join button...", index)
        await visible_locator(page, JOIN_BUTTONS).first.click()
        await name_input.wait_for(state="hidden")
        joined = True
        log(
            f"Join form closed after {time.monotonic() - started:.1f} s.",
            index,
        )
        return True
    except Exception as exc:
        log(f"Error during {stage}: {type(exc).__name__}: {exc}", index)
        if page is not None:
            screenshot = (
                Path(__file__).resolve().parent
                / "errors"
                / f"playwright-guest-{index + 1}.png"
            )
            try:
                screenshot.parent.mkdir(exist_ok=True)
                await page.screenshot(path=str(screenshot), timeout=5000)
                log(f"Error screenshot: {screenshot}", index)
            except Exception as screenshot_error:
                log(f"Could not save screenshot: {screenshot_error}", index)
        return False
    finally:
        if context is not None and not joined:
            try:
                await context.close()
            except Exception as close_error:
                log(f"Could not close context: {close_error}", index)
            else:
                contexts.remove(context)
                log("Failed session closed.", index)


async def launch_guests(browser, args, contexts) -> int:
    indices = iter(range(args.count))
    dispatch_lock = asyncio.Lock()
    next_start = 0.0

    async def worker():
        nonlocal next_start
        successes = 0
        while True:
            async with dispatch_lock:
                index = next(indices, None)
                if index is None:
                    return successes
                remaining = next_start - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                next_start = time.monotonic() + args.delay
            successes += await join_guest(browser, args, index, contexts)

    tasks = [
        asyncio.create_task(worker()) for _ in range(min(args.workers, args.count))
    ]
    try:
        return sum(await asyncio.gather(*tasks))
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def wait_for_enter() -> None:
    # Keep Playwright's event loop alive; no background input thread can hold
    # interpreter shutdown hostage after Ctrl+C. Supported by the Linux loop.
    loop = asyncio.get_running_loop()
    ready = loop.create_future()

    def readable():
        if not ready.done():
            ready.set_result(sys.stdin.readline())

    loop.add_reader(sys.stdin.fileno(), readable)
    try:
        if await ready == "":
            raise EOFError
    finally:
        loop.remove_reader(sys.stdin.fileno())


async def run(args) -> int:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        log(
            f"Launching one Chromium browser: guests={args.count}, workers={min(args.workers, args.count)}."
        )
        browser = await playwright.chromium.launch(
            headless=not args.headed,
            executable_path=args.chrome_binary,
            timeout=args.timeout * 1000,
            chromium_sandbox=True,
            args=["--mute-audio", "--disable-notifications", "--disable-extensions"],
        )
        contexts = []
        started = time.monotonic()
        try:
            successes = await launch_guests(browser, args, contexts)
            log(
                f"Join forms completed: {successes}/{args.count}; elapsed: {time.monotonic() - started:.1f} s."
            )
            if successes and not args.close:
                log("Sessions are open. Press Enter or Ctrl+C to close all sessions.")
                await wait_for_enter()
            return 0 if successes == args.count else 1
        finally:
            log(f"Closing {len(contexts)} contexts and Chromium...")
            try:
                results = await asyncio.gather(
                    *(context.close() for context in contexts), return_exceptions=True
                )
                for result in results:
                    if isinstance(result, BaseException):
                        log(f"Error closing context: {result}")
            finally:
                await browser.close()
            log("Chromium closed.")


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(run(args))
    except ModuleNotFoundError as exc:
        log(
            f"Missing dependency {exc.name}. Run: {sys.executable} -m pip install -r requirements.txt"
        )
        return 2
    except (KeyboardInterrupt, EOFError):
        log("Stopped.")
        return 130
    except Exception as exc:
        log(f"Error: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
