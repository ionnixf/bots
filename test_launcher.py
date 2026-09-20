import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import launcher
from services import SERVICES


class SelectionTests(unittest.TestCase):
    def test_explicit_service(self):
        for service in SERVICES:
            args = launcher.parse_args(["--service", service, "https://example.org"])
            self.assertEqual(args.service, service)

    def test_missing_or_invalid_service_is_rejected(self):
        for argv in (
            ["https://example.org"],
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
