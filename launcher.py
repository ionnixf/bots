#!/usr/bin/env python3
"""Shared launcher for Telemost and Kontur.Talk guest sessions."""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import sys
import time
from pathlib import Path

from services import SERVICES

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
        ("Александр", "Иван", "Дмитрий", "Сергей", "Павел"),
        ("Иванов", "Петров", "Смирнов", "Соколов", "Морозов"),
    ),
    (
        ("Мария", "Елена", "Анна", "Ольга", "Татьяна"),
        ("Иванова", "Петрова", "Смирнова", "Соколова", "Морозова"),
    ),
)


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


def guest_name(args) -> str:
    """Return the shared name when configured, otherwise generate one."""
    if args.name is not None:
        return args.name
    return random_name(args.name_language)


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


def non_empty_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise argparse.ArgumentTypeError("must not be empty")
    return name


def parse_args(argv=None, *, default_service=None):
    parser = argparse.ArgumentParser(
        description=(
            "Join Telemost or Kontur.Talk with isolated Playwright guest sessions."
        )
    )
    parser.add_argument(
        "--service",
        choices=tuple(SERVICES),
        default=default_service,
        required=default_service is None,
        help="meeting service",
    )
    parser.add_argument("url", help="meeting or event URL (required)")
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
        help="language of random guest names (default: en)",
    )
    parser.add_argument(
        "--name",
        type=non_empty_name,
        help="use this same guest name for every session instead of random names",
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
    service = SERVICES[args.service]
    context = None
    page = None
    joined = False
    stage = "context creation"
    started = time.monotonic()
    name = guest_name(args)
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

        if service.warning_buttons:
            warnings = visible_locator(page, service.warning_buttons).last

            async def dismiss_warning():
                log("Dismissing camera/microphone warning...", index)
                await warnings.click()

            await page.add_locator_handler(
                warnings, dismiss_warning, no_wait_after=True
            )

        stage = "page navigation"
        log(f"Opening {service.label}...", index)
        await page.goto(args.url, wait_until="domcontentloaded")

        stage = "waiting for the join form"
        name_input = visible_locator(page, service.name_inputs).first
        if service.continue_buttons:
            continuation = visible_locator(page, service.continue_buttons).first
            await name_input.or_(continuation).first.wait_for()
            if not await name_input.is_visible():
                await continuation.click()
                log("Clicked 'Continue in browser'.", index)
        else:
            await name_input.wait_for()

        stage = "entering guest name"
        await name_input.fill(name)
        # Blur commits the field in applications that update state on change.
        await name_input.press("Tab")
        log(f"Entered name: {name}.", index)

        stage = "joining"
        log("Clicking the join button...", index)
        await visible_locator(page, service.join_buttons).first.click()
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
                / f"{args.service}-guest-{index + 1}.png"
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
            f"Launching one Chromium browser: guests={args.count}, "
            f"workers={min(args.workers, args.count)}."
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
                f"Join forms completed: {successes}/{args.count}; "
                f"elapsed: {time.monotonic() - started:.1f} s."
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


def main(argv=None, *, default_service=None) -> int:
    args = parse_args(argv, default_service=default_service)
    try:
        return asyncio.run(run(args))
    except ModuleNotFoundError as exc:
        project_dir = Path(__file__).resolve().parent
        local_venv = project_dir / ".venv"
        local_python = local_venv / "bin" / "python"
        if (
            exc.name == "playwright"
            and local_python.is_file()
            and Path(sys.prefix).resolve() != local_venv.resolve()
        ):
            command_args = sys.argv[1:] if argv is None else list(argv)
            log(f"Playwright is installed in {local_python}; restarting with it.")
            os.execv(
                str(local_python),
                [
                    str(local_python),
                    str(Path(__file__).resolve()),
                    "--service",
                    args.service,
                    *command_args,
                ],
            )
        log(
            f"Missing dependency {exc.name}. Run: "
            f"{sys.executable} -m pip install -r requirements.txt"
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
