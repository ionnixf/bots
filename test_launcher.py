import asyncio
import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import launcher
from services import SERVICES


class SelectionTests(unittest.TestCase):
    def test_service_detected_from_url_in_all_entry_points(self):
        for url, expected in (
            ("https://telemost.yandex.ru/j/test", "telemost"),
            ("https://telemost.yandex.com/j/test", "telemost"),
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

    def test_explicit_service(self):
        for service in SERVICES:
            args = launcher.parse_args(["--service", service, "https://example.org"])
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
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--service", result.stdout)


class TelemostFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_and_browser_continuation_entry(self):
        for direct in (True, False):
            with self.subTest(direct=direct):
                name = Mock(
                    fill=AsyncMock(),
                    press=AsyncMock(),
                    wait_for=AsyncMock(),
                    is_visible=AsyncMock(return_value=direct),
                )
                name.or_.return_value.first.wait_for = AsyncMock()
                continuation = Mock(click=AsyncMock())
                join = Mock(click=AsyncMock())
                warning = Mock(click=AsyncMock())
                page = Mock(goto=AsyncMock(), add_locator_handler=AsyncMock())
                context = Mock(
                    grant_permissions=AsyncMock(),
                    route=AsyncMock(),
                    new_page=AsyncMock(return_value=page),
                )
                browser = Mock(new_context=AsyncMock(return_value=context))
                args = launcher.parse_args(
                    [
                        "--service",
                        "telemost",
                        "https://telemost.yandex.ru/j/test",
                        "--name",
                        "Test Guest",
                    ]
                )
                with patch.object(
                    launcher,
                    "visible_locator",
                    side_effect=[
                        SimpleNamespace(last=warning),
                        SimpleNamespace(first=name),
                        SimpleNamespace(first=continuation),
                        SimpleNamespace(first=join),
                    ],
                ):
                    self.assertTrue(await launcher.join_guest(browser, args, 0, []))
                name.fill.assert_awaited_once_with("Test Guest")
                join.click.assert_awaited_once()
                name.wait_for.assert_awaited_once_with(state="hidden")
                self.assertEqual(continuation.click.await_count, int(not direct))
                page.add_locator_handler.assert_awaited_once()
                handler = page.add_locator_handler.call_args.args[1]
                await handler()
                warning.click.assert_awaited_once()


TEST_URL = "https://telemost.yandex.ru/j/test-meeting"


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

    async def test_failed_setup_closes_context(self):
        context = Mock()
        context.grant_permissions = AsyncMock(side_effect=RuntimeError("denial failed"))
        context.close = AsyncMock()
        browser = Mock(new_context=AsyncMock(return_value=context))
        contexts = []
        self.assertFalse(
            await launcher.join_guest(
                browser, launcher.parse_args([TEST_URL]), 0, contexts
            )
        )
        context.close.assert_awaited_once()
        self.assertEqual(contexts, [])


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
                if default is not None:
                    with (
                        contextlib.redirect_stderr(io.StringIO()),
                        self.assertRaises(SystemExit) as error,
                    ):
                        launcher.parse_args([url], default_service=default)
                    self.assertEqual(error.exception.code, 2)

    def test_url_is_required(self):
        with self.assertRaises(SystemExit) as error:
            launcher.parse_args([])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
