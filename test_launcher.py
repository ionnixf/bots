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


if __name__ == "__main__":
    unittest.main()
