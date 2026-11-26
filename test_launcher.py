import asyncio
import contextlib
import io
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import launcher
from services import SERVICES

TEST_URL = "https://telemost.yandex.ru/j/test-meeting"
PRIVATE_FRAME = "https://telemost.yandex.ru/private-join/123?lang=ru&mic=on&camera=on"

VISIBLE_FLAGS = {
    "name": "name_visible",
    "join": "join_visible",
    "continue": "continue_visible",
    "overlay": "overlay_visible",
    "mic": "mic_off_visible",
    "camera": "camera_off_visible",
    "joined": "joined_visible",
}
SELECTOR_KINDS = (
    ("meeting-continue-in-browser", "continue"),
    ("Продолжить в браузере", "continue"),
    ("Continue in browser", "continue"),
    ("telemost-3-onboarding", "overlay"),
    ("Понятно", "overlay"),
    ("Got it", "overlay"),
    ("turn-off-mic", "mic"),
    ("Выключить микрофон", "mic"),
    ("turn-off-camera", "camera"),
    ("Выключить камеру", "camera"),
    ("end-call-alt", "joined"),
    ("participants-button", "joined"),
    ("enter-conference-button", "join"),
    ("Подключиться", "join"),
    ("Присоединиться", "join"),
    ("normalize-space(.)='Продолжить'", "join"),
    ("'Continue'", "join"),
    ("orb-textinput-input", "name"),
    ("autocomplete='name'", "name"),
    ("placeholder*='имя'", "name"),
    ("placeholder*='name'", "name"),
    ("AnonymousAuthorization.Input", "name"),
    ("AnonymousAuthorization.Anonymous", "join"),
    ("Сергей Иванов", "name"),
)


def selector_kind(selector: str) -> str | None:
    if selector == "body":
        return "body"
    for token, kind in SELECTOR_KINDS:
        if token in selector:
            return kind
    return None


class UIState:
    def __init__(self, **overrides):
        self.name_visible = True
        self.join_visible = True
        self.continue_visible = False
        self.overlay_visible = False
        self.mic_off_visible = True
        self.camera_off_visible = True
        self.joined_visible = False
        self.text = ""
        self.close_form_on_join = True
        self.join_noop = False
        self.filled = []
        self.fill_urls = []
        self.keys = []
        self.clicks = []
        self.goto_urls = []
        self.screenshots = []
        self.context_closed = False
        self.on_direct = None
        for name, value in overrides.items():
            setattr(self, name, value)


class FakeLocator:
    def __init__(self, state, selectors, frame):
        self.state = state
        self.selectors = tuple(selectors)
        self.frame = frame

    def or_(self, other):
        return FakeLocator(self.state, (*self.selectors, *other.selectors), self.frame)

    def filter(self, **kwargs):
        return self

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def kinds(self):
        return {selector_kind(selector) for selector in self.selectors}

    def owns(self, kind) -> bool:
        elements = self.frame.elements
        return elements is None or kind in elements

    async def is_visible(self) -> bool:
        for kind in self.kinds():
            if kind == "body":
                return True
            if (
                kind in VISIBLE_FLAGS
                and self.owns(kind)
                and getattr(self.state, VISIBLE_FLAGS[kind])
            ):
                return True
        return False

    async def fill(self, text):
        self.state.filled.append(text)
        self.state.fill_urls.append(self.frame.url)

    async def press(self, key):
        self.state.keys.append(key)

    async def inner_text(self, timeout=None):
        return self.state.text

    async def click(self, timeout=None):
        kinds = self.kinds()
        kind = next((name for name in kinds if name != "body"), None)
        self.state.clicks.append(kind)
        if kind == "continue":
            self.state.continue_visible = False
        elif kind == "overlay":
            self.state.overlay_visible = False
        elif kind == "mic":
            self.state.mic_off_visible = False
        elif kind == "camera":
            self.state.camera_off_visible = False
        elif (
            kind == "join"
            and not self.state.join_noop
            and self.state.close_form_on_join
        ):
            self.state.name_visible = False
            self.state.join_visible = False


class FakeFrame:
    def __init__(self, state, url="", elements=None):
        self.state = state
        self.url = url
        self.elements = elements

    def locator(self, selector):
        return FakeLocator(self.state, (selector,), self)


class FakePage:
    def __init__(self, state, frames):
        self.state = state
        self._frames = list(frames)
        self.main_frame = self._frames[-1]
        self.url = self.main_frame.url

    @property
    def frames(self):
        return list(self._frames)

    async def goto(self, url, wait_until=None):
        self.state.goto_urls.append(url)
        self.url = url
        if "/private-join/" in url:
            frame = FakeFrame(self.state, url, None)
            self._frames = [frame]
            self.main_frame = frame
            if self.state.on_direct is not None:
                self.state.on_direct(url)

    async def screenshot(self, path, timeout=None):
        self.state.screenshots.append(path)


class FakeContext:
    def __init__(self, state, page, fail_permissions=False):
        self.state = state
        self.page = page
        self.fail_permissions = fail_permissions
        self.permissions = []
        self.routes = []
        self.default_timeout = None

    async def grant_permissions(self, permissions):
        if self.fail_permissions:
            raise RuntimeError("permission grant failed")
        self.permissions = list(permissions)

    async def route(self, pattern, handler):
        self.routes.append(pattern)

    def set_default_timeout(self, milliseconds):
        self.default_timeout = milliseconds

    async def new_page(self):
        return self.page

    async def close(self):
        self.state.context_closed = True


class FakeBrowser:
    def __init__(self, context):
        self.context = context
        self.context_options = []

    async def new_context(self, **kwargs):
        self.context_options.append(kwargs)
        return self.context


def build_environment(
    *,
    main_elements=(),
    child_elements=("name", "join", "mic", "camera"),
    with_child=True,
    **state_options,
):
    state = UIState(**state_options)
    frames = []
    if with_child:
        frames.append(FakeFrame(state, PRIVATE_FRAME, set(child_elements)))
    frames.append(FakeFrame(state, TEST_URL, set(main_elements)))
    page = FakePage(state, frames)
    context = FakeContext(state, page)
    return state, page, context, FakeBrowser(context)


@contextmanager
def fast_engine():
    with patch.multiple(
        launcher,
        POLL_INTERVAL=0.0,
        CLICK_COOLDOWN=0.0,
        JOIN_GRACE=0.0,
    ):
        yield


def telemost_args(*extra):
    return launcher.parse_args(
        [
            "--service",
            "telemost",
            TEST_URL,
            "--name",
            "Test Guest",
            "--join-timeout",
            "5",
            *extra,
        ]
    )


class ServiceSelectionTests(unittest.TestCase):
    def test_service_detected_from_url_in_all_entry_points(self):
        for url, expected in (
            ("https://telemost.yandex.ru/j/test", "telemost"),
            ("https://telemost.yandex.com/j/test", "telemost"),
            ("https://telemost.360.yandex.ru/j/test", "telemost"),
            ("https://TELEMOST.YANDEX.RU:443/j/test?x=ktalk.ru", "telemost"),
            ("https://ktalk.ru/test", "ktalk"),
            ("https://company.ktalk.ru/event/test", "ktalk"),
            ("https://COMPANY.KTALK.RU./test", "ktalk"),
        ):
            for default in (None, "telemost", "ktalk"):
                with self.subTest(url=url, default=default):
                    args = launcher.parse_args([url], default_service=default)
                    self.assertEqual(args.service, expected)
                    self.assertEqual(args.url, url)

    def test_explicit_service_overrides_detection_and_entry_point(self):
        args = launcher.parse_args(
            ["https://telemost.yandex.ru/j/test", "--service", "ktalk"],
            default_service="telemost",
        )
        self.assertEqual(args.service, "ktalk")

    def test_entry_point_default_for_custom_domains(self):
        for service in SERVICES:
            args = launcher.parse_args(
                ["https://meet.example.org/test"], default_service=service
            )
            self.assertEqual(args.service, service)

    def test_missing_or_invalid_service_is_rejected(self):
        for argv in (
            ["https://example.org"],
            ["https://ktalk.ru.example.org/test"],
            ["https://fakektalk.ru/test"],
            ["https://telemost.yandex.ru.example.org/j/test"],
            ["https://example.org/ktalk.ru?url=telemost.yandex.ru"],
            ["https://ktalk.ru@example.org/test"],
            ["ftp://company.ktalk.ru/test"],
            ["https://[invalid/test"],
            ["--service", "other", "https://example.org"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as error:
                launcher.parse_args(argv)
            self.assertEqual(error.exception.code, 2)

    def test_entry_points_help(self):
        root = Path(__file__).resolve().parent
        for script in ("main.py", "telemost.py", "ktalk.py"):
            result = subprocess.run(
                [sys.executable, str(root / script), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--service", result.stdout)
            self.assertIn("--join-timeout", result.stdout)


class TelemostJoinTests(unittest.IsolatedAsyncioTestCase):
    async def test_joins_from_embedded_iframe_and_disables_devices(self):
        state, _page, context, browser = build_environment()
        contexts = []
        with fast_engine():
            joined = await launcher.join_guest(browser, telemost_args(), 0, contexts)

        self.assertTrue(joined)
        self.assertEqual(contexts, [context])
        self.assertEqual(state.filled, ["Test Guest"])
        self.assertEqual(state.fill_urls, [PRIVATE_FRAME])
        self.assertEqual(state.keys, ["Tab"])
        self.assertIn("join", state.clicks)
        self.assertIn("mic", state.clicks)
        self.assertIn("camera", state.clicks)
        self.assertFalse(state.context_closed)
        self.assertEqual(context.permissions, ["microphone", "camera"])
        self.assertEqual(
            browser.context_options[0],
            {"viewport": {"width": 960, "height": 720}, "service_workers": "block"},
        )

    async def test_continue_in_browser_and_dialogs_are_clicked_first(self):
        state, _page, _context, browser = build_environment(
            main_elements=("continue", "overlay"),
            continue_visible=True,
            overlay_visible=True,
        )
        contexts = []
        with fast_engine():
            joined = await launcher.join_guest(browser, telemost_args(), 0, contexts)

        self.assertTrue(joined)
        self.assertEqual(state.clicks[:2], ["continue", "overlay"])
        self.assertFalse(state.continue_visible)
        self.assertFalse(state.overlay_visible)
        self.assertEqual(state.filled, ["Test Guest"])

    async def test_failure_marker_stops_the_guest(self):
        state, _page, _context, browser = build_environment(
            text="Такого звонка нет. Проверьте ссылку."
        )
        contexts = []
        screenshot = AsyncMock(return_value=Path("errors/telemost-guest-1.png"))
        with (
            fast_engine(),
            patch.object(launcher, "save_error_screenshot", screenshot),
        ):
            joined = await launcher.join_guest(browser, telemost_args(), 0, contexts)

        self.assertFalse(joined)
        self.assertTrue(state.context_closed)
        self.assertEqual(contexts, [])
        screenshot.assert_awaited_once()

    async def test_lobby_marker_proves_the_join(self):
        state, _page, _context, browser = build_environment(
            text="Зал ожидания. Организатор скоро впустит вас."
        )
        contexts = []
        with fast_engine():
            joined = await launcher.join_guest(browser, telemost_args(), 0, contexts)
        self.assertTrue(joined)
        self.assertEqual(state.filled, [])
        self.assertFalse(state.context_closed)

    async def test_closed_form_without_markers_counts_as_joined(self):
        state, _page, _context, browser = build_environment()
        contexts = []
        with fast_engine():
            joined = await launcher.join_guest(browser, telemost_args(), 0, contexts)
        self.assertTrue(joined)
        self.assertEqual(state.clicks.count("join"), 1)

    async def test_stuck_embedded_form_opens_join_frame_directly(self):
        state, _page, _context, browser = build_environment(join_noop=True)
        state.on_direct = lambda url: setattr(state, "join_noop", False)
        contexts = []
        with fast_engine():
            joined = await launcher.join_guest(browser, telemost_args(), 0, contexts)

        self.assertTrue(joined)
        direct_url = state.goto_urls[-1]
        self.assertIn("/private-join/123", direct_url)
        self.assertIn("mic=off", direct_url)
        self.assertIn("camera=off", direct_url)
        self.assertIn("lang=ru", direct_url)
        self.assertEqual(state.fill_urls[-1], direct_url)

    async def test_permission_failure_closes_the_context(self):
        state = UIState()
        page = FakePage(state, [FakeFrame(state, TEST_URL)])
        context = FakeContext(state, page, fail_permissions=True)
        browser = FakeBrowser(context)
        contexts = []
        self.assertFalse(
            await launcher.join_guest(browser, telemost_args(), 0, contexts)
        )
        self.assertTrue(state.context_closed)
        self.assertEqual(contexts, [])

    async def test_context_grants_fake_devices_and_blocks_images(self):
        context = Mock(grant_permissions=AsyncMock(), route=AsyncMock())
        await launcher.configure_context(context, load_images=False)
        context.grant_permissions.assert_awaited_once_with(["microphone", "camera"])
        context.route.assert_awaited_once()

        context = Mock(grant_permissions=AsyncMock(), route=AsyncMock())
        await launcher.configure_context(context, load_images=True)
        context.route.assert_not_awaited()


class KTalkFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_frame_form_is_supported(self):
        state, _page, _context, browser = build_environment(
            with_child=False, main_elements=("name", "join")
        )
        args = launcher.parse_args(
            [
                "--service",
                "ktalk",
                "https://example.ktalk.ru/event/test",
                "--name",
                "Test Guest",
                "--join-timeout",
                "5",
            ]
        )
        contexts = []
        with fast_engine():
            joined = await launcher.join_guest(browser, args, 0, contexts)
        self.assertTrue(joined)
        self.assertEqual(state.filled, ["Test Guest"])


class ParallelTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_concurrency_and_partial_failure(self):
        active = peak = 0
        both_started = asyncio.Event()

        async def join(browser, args, index, contexts):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), 2)
            await asyncio.sleep(0)
            active -= 1
            return index != 1

        with patch.object(launcher, "join_guest", side_effect=join):
            total = await launcher.launch_guests(
                Mock(),
                launcher.parse_args([TEST_URL, "-n", "5", "--workers", "2"]),
                [],
            )
        self.assertEqual(total, 4)
        self.assertEqual(peak, 2)

    async def test_cancel_workers_before_returning(self):
        started = asyncio.Event()
        finished = asyncio.Event()

        async def join(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()

        with patch.object(launcher, "join_guest", side_effect=join):
            task = asyncio.create_task(
                launcher.launch_guests(
                    Mock(),
                    launcher.parse_args([TEST_URL, "-n", "3", "--workers", "1"]),
                    [],
                )
            )
            await asyncio.wait_for(started.wait(), 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(finished.is_set())


class GuestNameTests(unittest.TestCase):
    def test_random_name_is_generated_when_name_is_not_set(self):
        args = launcher.parse_args([TEST_URL, "--name-language", "ru"])
        with patch.object(
            launcher, "random_name", return_value="Иван Иванов"
        ) as generate:
            self.assertEqual(launcher.guest_name(args), "Иван Иванов")
        generate.assert_called_once_with("ru")

    def test_configured_name_is_shared_without_random_generation(self):
        args = launcher.parse_args([TEST_URL, "--name", "  Общий гость  "])
        with patch.object(launcher, "random_name") as generate:
            self.assertEqual(launcher.guest_name(args), "Общий гость")
        generate.assert_not_called()

    def test_empty_configured_name_is_rejected(self):
        with self.assertRaises(SystemExit):
            launcher.parse_args([TEST_URL, "--name", "   "])


class ArgumentTests(unittest.TestCase):
    def test_invalid_url_is_rejected_even_with_service_override_or_fallback(self):
        for url in (
            "ktalk.ru/test",
            "ftp://ktalk.ru/test",
            "https://",
            "https://[bad",
            "https://ktalk.ru:bad/test",
        ):
            for default in (None, "telemost", "ktalk"):
                with (
                    self.subTest(url=url, default=default),
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as error,
                ):
                    launcher.parse_args(
                        [url, "--service", "ktalk"], default_service=default
                    )
                self.assertEqual(error.exception.code, 2)

    def test_join_timeout_must_be_positive(self):
        for value in ("0", "-1", "abc"):
            with (
                self.subTest(value=value),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                launcher.parse_args([TEST_URL, "--join-timeout", value])
            self.assertEqual(error.exception.code, 2)

    def test_url_is_required(self):
        with self.assertRaises(SystemExit) as error:
            launcher.parse_args([])
        self.assertEqual(error.exception.code, 2)


class InterpreterFallbackTests(unittest.TestCase):
    def test_main_restarts_with_project_venv_when_playwright_is_missing(self):
        missing = ModuleNotFoundError(
            "No module named 'playwright'",
            name="playwright",
        )
        with (
            patch.object(launcher, "run", AsyncMock(side_effect=missing)),
            patch.object(launcher.os, "execv") as execute,
            patch.object(launcher.sys, "executable", "/usr/bin/python"),
            patch.object(launcher.sys, "prefix", "/usr"),
            patch.object(launcher.Path, "is_file", return_value=True),
        ):
            launcher.main(
                ["https://example.ktalk.ru/event/test", "--close"],
                default_service="ktalk",
            )

        local_python = (
            launcher.Path(launcher.__file__).resolve().parent / ".venv/bin/python"
        )
        execute.assert_called_once_with(
            str(local_python),
            [
                str(local_python),
                str(launcher.Path(launcher.__file__).resolve()),
                "--service",
                "ktalk",
                "https://example.ktalk.ru/event/test",
                "--close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
