#!/usr/bin/env python3
"""Shared launcher for meeting services: frame-aware, provider-neutral joining."""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from media import build_fake_media_args
from services import SERVICES, detect_service

DEFAULT_COUNT = 15

# Join-engine pacing. Tests patch these to keep the loop instant.
POLL_INTERVAL = 1.0
JOIN_GRACE = 8.0
CLICK_COOLDOWN = 4.0
MAX_JOIN_CLICKS = 4
DIRECT_FALLBACK_AFTER = 2
MAX_OVERLAY_CLICKS = 6
FRAME_TEXT_TIMEOUT_MS = 1_000
CLICK_TIMEOUT_MS = 3_000
SCREENSHOT_TIMEOUT_MS = 5_000

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


def meeting_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ("http", "https") and parsed.hostname:
            _ = parsed.port  # Validate an explicitly supplied port too.
            return value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("must be a full http:// or https:// meeting URL")


def parse_args(argv=None, *, default_service=None):
    parser = argparse.ArgumentParser(
        description="Join a supported meeting service with isolated Playwright guests.",
    )
    parser.add_argument(
        "--service",
        choices=tuple(SERVICES),
        help=(
            "override the provider detected from URL"
            + (
                f"; unknown domains fall back to {default_service}"
                if default_service
                else ""
            )
        ),
    )
    parser.add_argument(
        "url", type=meeting_url, help="full http:// or https:// meeting URL"
    )
    parser.add_argument(
        "-n",
        "--count",
        type=positive_int,
        default=DEFAULT_COUNT,
        help="total guest sessions (default: %(default)s)",
    )
    parser.add_argument(
        "--name-language",
        choices=("ru", "en"),
        default="en",
        help="language of random guest names; ignored with --name (default: %(default)s)",
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
        help="maximum concurrent join attempts (default: %(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=non_negative_float,
        default=0.0,
        help="minimum interval between starting join attempts, in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=30,
        help="browser launch and per-action timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--join-timeout",
        type=positive_int,
        default=180,
        help="maximum seconds spent on one guest's join form (default: %(default)s)",
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
    args = parser.parse_args(argv)
    args.service = args.service or detect_service(args.url) or default_service
    if args.service is None:
        choices = " or ".join(f"--service {key}" for key in SERVICES)
        parser.error(f"cannot detect the meeting service from URL; specify {choices}")
    return args


# ---------------------------------------------------------------------------
# Locator and frame helpers


def visible_locator(frame, selectors):
    """Combine locator alternatives into one visible-only locator."""
    result = None
    for by, selector in selectors:
        locator = frame.locator(f"xpath={selector}" if by == "xpath" else selector)
        result = locator if result is None else result.or_(locator)
    return None if result is None else result.filter(visible=True)


async def first_visible(frame, selectors):
    """Return the first visible match in one frame, or ``None``."""
    locator = visible_locator(frame, selectors)
    if locator is None:
        return None
    candidate = locator.first
    try:
        return candidate if await candidate.is_visible() else None
    except Exception:  # noqa: BLE001 - frames can detach while loading
        # Frames can detach at any moment while a meeting page is loading.
        return None


def ordered_frames(page, service):
    """Prefer embedded join frames over the outer page shell."""
    patterns = tuple(re.compile(p) for p in service.frame_url_patterns)
    main = page.main_frame
    others = [frame for frame in page.frames if frame is not main]

    def priority(frame):
        url = frame.url or ""
        return 0 if any(pattern.search(url) for pattern in patterns) else 1

    others.sort(key=priority)
    return [*others, main]


async def find_visible_any(page, service, selectors):
    """Search every frame, join frames first, and return a live locator."""
    for frame in ordered_frames(page, service):
        found = await first_visible(frame, selectors)
        if found is not None:
            return found
    return None


async def click_visible_any(page, service, selectors) -> bool:
    found = await find_visible_any(page, service, selectors)
    if found is None:
        return False
    try:
        await found.click(timeout=CLICK_TIMEOUT_MS)
    except Exception:  # noqa: BLE001 - the frame may be replaced
        return False
    return True


@dataclass
class JoinTarget:
    frame: object
    name_input: object = None
    join_button: object = None


async def find_join_target(page, service) -> JoinTarget | None:
    """Find the frame that owns the guest join form.

    A frame with a join button wins over a frame that only exposes a name field,
    which keeps the outer shell from being mistaken for the guest form.
    """
    name_only = None
    for frame in ordered_frames(page, service):
        join_button = await first_visible(frame, service.join_buttons)
        name_input = await first_visible(frame, service.name_inputs)
        if join_button is not None:
            return JoinTarget(frame, name_input, join_button)
        if name_input is not None and name_only is None:
            name_only = JoinTarget(frame, name_input, None)
    return name_only


async def frame_text(frame) -> str:
    try:
        return await frame.locator("body").inner_text(timeout=FRAME_TEXT_TIMEOUT_MS)
    except Exception:  # noqa: BLE001 - a detached frame has no text
        return ""


async def page_text(page) -> str:
    parts = []
    for frame in page.frames:
        text = await frame_text(frame)
        if text:
            parts.append(text)
    return "\n".join(parts).casefold()


def find_marker(markers, text: str) -> str | None:
    for marker in markers:
        if marker.casefold() in text:
            return marker
    return None


# ---------------------------------------------------------------------------
# Join-engine helpers


def with_params(url: str, params: tuple[tuple[str, str], ...]) -> str:
    """Force query parameters while preserving every other part of the URL."""
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit(parts._replace(query=urlencode(query)))


def direct_frame_url(page, service) -> str | None:
    """Return the current guest-frame URL with forced quiet-device params."""
    patterns = tuple(re.compile(p) for p in service.frame_url_patterns)
    candidates = [page.url, *(frame.url for frame in page.frames)]
    for url in candidates:
        if url and any(pattern.search(url) for pattern in patterns):
            return with_params(url, service.direct_frame_params)
    return None


async def save_error_screenshot(page, service_key: str, index: int) -> Path:
    screenshot = (
        Path(__file__).resolve().parent
        / "errors"
        / f"{service_key}-guest-{index + 1}.png"
    )
    screenshot.parent.mkdir(exist_ok=True)
    await page.screenshot(path=str(screenshot), timeout=SCREENSHOT_TIMEOUT_MS)
    return screenshot


async def configure_context(context, load_images: bool) -> None:
    # Fake capture devices satisfy camera/microphone requests, so no real
    # hardware or permission prompt is involved.
    await context.grant_permissions(["microphone", "camera"])
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
    deadline = started + args.join_timeout
    name = guest_name(args)
    name_filled = False
    join_clicks = 0
    last_click = 0.0
    overlay_clicks = 0
    continue_clicked = False
    mic_off_done = False
    camera_off_done = False
    fallback_used = False
    form_gone_since = None
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

        stage = "page navigation"
        log(f"Opening {service.label}...", index)
        await page.goto(args.url, wait_until="domcontentloaded")

        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"join form did not complete within {args.join_timeout} s"
                )

            stage = "checking the meeting page"
            text = await page_text(page)

            failure = find_marker(service.failure_markers, text)
            if failure is not None:
                raise RuntimeError(f"meeting page reports {failure!r}")

            joined_marker = find_marker(service.joined_markers, text)
            if joined_marker is not None:
                joined = True
                log(
                    f"Joined ({joined_marker!r}) after "
                    f"{time.monotonic() - started:.1f} s.",
                    index,
                )
                return True

            if service.joined_buttons:
                controls = await find_visible_any(page, service, service.joined_buttons)
                if controls is not None:
                    joined = True
                    log(
                        f"Meeting controls detected after "
                        f"{time.monotonic() - started:.1f} s.",
                        index,
                    )
                    return True

            stage = "waiting for the join form"
            target = await find_join_target(page, service)

            if target is None:
                if join_clicks:
                    now = time.monotonic()
                    if form_gone_since is None:
                        form_gone_since = now
                    elif now - form_gone_since >= JOIN_GRACE:
                        joined = True
                        log(
                            "Join form stayed closed; treating the guest as joined.",
                            index,
                        )
                        return True
                await asyncio.sleep(POLL_INTERVAL)
                continue

            form_gone_since = None

            if (
                service.continue_buttons
                and not continue_clicked
                and await click_visible_any(page, service, service.continue_buttons)
            ):
                continue_clicked = True
                log("Clicked 'Continue in browser'.", index)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if (
                service.overlay_buttons
                and overlay_clicks < MAX_OVERLAY_CLICKS
                and await click_visible_any(page, service, service.overlay_buttons)
            ):
                overlay_clicks += 1
                log("Dismissed a blocking dialog.", index)
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if target.name_input is not None and not name_filled:
                stage = "entering guest name"
                await target.name_input.fill(name)
                # Blur commits the field in apps that update state on change.
                await target.name_input.press("Tab")
                name_filled = True
                log(f"Entered name: {name}.", index)

            if (
                service.mic_off_buttons
                and not mic_off_done
                and await click_visible_any(page, service, service.mic_off_buttons)
            ):
                mic_off_done = True
                log("Microphone switched off.", index)

            if (
                service.camera_off_buttons
                and not camera_off_done
                and await click_visible_any(page, service, service.camera_off_buttons)
            ):
                camera_off_done = True
                log("Camera switched off.", index)

            now = time.monotonic()
            fallback_ready = (
                bool(service.direct_frame_params)
                and join_clicks >= DIRECT_FALLBACK_AFTER
                and not fallback_used
                and target.name_input is not None
                and now - last_click >= CLICK_COOLDOWN
            )
            if fallback_ready:
                direct_url = direct_frame_url(page, service)
                if direct_url is not None:
                    stage = "direct join-frame navigation"
                    log(
                        "Embedded join form is stuck; opening it directly.",
                        index,
                    )
                    await page.goto(direct_url, wait_until="domcontentloaded")
                    fallback_used = True
                    name_filled = False
                    mic_off_done = False
                    camera_off_done = False
                    form_gone_since = None
                    last_click = time.monotonic()
                    continue
                # Do not retry a fallback the page cannot provide.
                fallback_used = True

            if target.join_button is not None:
                if join_clicks >= MAX_JOIN_CLICKS:
                    raise RuntimeError("join button did not respond")
                if now - last_click >= CLICK_COOLDOWN:
                    stage = "joining"
                    log("Clicking the join button...", index)
                    join_clicks += 1
                    last_click = time.monotonic()
                    try:
                        await target.join_button.click(timeout=CLICK_TIMEOUT_MS)
                    except Exception as exc:  # noqa: BLE001 - retried next poll
                        log(
                            f"Join click failed: {type(exc).__name__}: {exc}",
                            index,
                        )

            await asyncio.sleep(POLL_INTERVAL)
    except Exception as exc:  # noqa: BLE001 - report any guest failure
        log(f"Error during {stage}: {type(exc).__name__}: {exc}", index)
        if page is not None:
            try:
                screenshot = await save_error_screenshot(page, args.service, index)
                log(f"Error screenshot: {screenshot}", index)
            except Exception as screenshot_error:  # noqa: BLE001
                log(f"Could not save screenshot: {screenshot_error}", index)
        return False
    finally:
        if context is not None and not joined:
            try:
                await context.close()
            except Exception as close_error:  # noqa: BLE001
                log(f"Could not close context: {close_error}", index)
            else:
                if context in contexts:
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

    try:
        media_args = build_fake_media_args()
    except Exception as exc:  # noqa: BLE001 - media is optional
        media_args = []
        log(f"Could not prepare fake media: {type(exc).__name__}: {exc}")

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
            args=[
                "--mute-audio",
                "--disable-notifications",
                "--disable-extensions",
                *media_args,
            ],
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
            log(f"Retrying with project interpreter: {local_python}.")
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
    except Exception as exc:  # noqa: BLE001 - top-level error report
        log(f"Error: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
