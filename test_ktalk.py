import unittest
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

import launcher as app
from services import SERVICES

parse_args = partial(app.parse_args, default_service="ktalk")

TEST_URL = "https://example.ktalk.ru/event/test-event"


class KTalkJoinTests(unittest.IsolatedAsyncioTestCase):
    async def test_anonymous_name_and_continue_flow(self):
        name_input = Mock(
            wait_for=AsyncMock(),
            fill=AsyncMock(),
            press=AsyncMock(),
        )
        continue_button = Mock(click=AsyncMock())
        page = Mock(goto=AsyncMock())
        context = Mock(
            grant_permissions=AsyncMock(),
            route=AsyncMock(),
            new_page=AsyncMock(return_value=page),
        )
        browser = Mock(new_context=AsyncMock(return_value=context))
        contexts = []

        with patch.object(
            app,
            "visible_locator",
            side_effect=(
                SimpleNamespace(first=name_input),
                SimpleNamespace(first=continue_button),
            ),
        ) as locate:
            joined = await app.join_guest(
                browser,
                parse_args([TEST_URL, "--name", "Test Guest"]),
                0,
                contexts,
            )

        self.assertTrue(joined)
        self.assertEqual(contexts, [context])
        page.goto.assert_awaited_once_with(TEST_URL, wait_until="domcontentloaded")
        name_input.fill.assert_awaited_once_with("Test Guest")
        name_input.press.assert_awaited_once_with("Tab")
        continue_button.click.assert_awaited_once()
        self.assertEqual(
            name_input.wait_for.await_args_list,
            [call(), call(state="hidden")],
        )
        self.assertEqual(
            locate.call_args_list,
            [
                call(page, SERVICES["ktalk"].name_inputs),
                call(page, SERVICES["ktalk"].join_buttons),
            ],
        )


class SelectorTests(unittest.TestCase):
    def test_selectors_target_ktalk_anonymous_authorization(self):
        self.assertIn(
            "AnonymousAuthorization.Input", SERVICES["ktalk"].name_inputs[0][1]
        )
        self.assertIn(
            "AnonymousAuthorization.Anonymous", SERVICES["ktalk"].join_buttons[0][1]
        )


class InterpreterFallbackTests(unittest.TestCase):
    def test_main_restarts_with_project_venv_when_playwright_is_missing(self):
        missing = ModuleNotFoundError(
            "No module named 'playwright'",
            name="playwright",
        )
        with (
            patch.object(app, "run", AsyncMock(side_effect=missing)),
            patch.object(app.os, "execv") as execute,
            patch.object(app.sys, "executable", "/usr/bin/python"),
            patch.object(app.sys, "prefix", "/usr"),
            patch.object(app.Path, "is_file", return_value=True),
        ):
            app.main([TEST_URL, "--close"], default_service="ktalk")

        local_python = app.Path(app.__file__).resolve().parent / ".venv/bin/python"
        execute.assert_called_once_with(
            str(local_python),
            [
                str(local_python),
                str(app.Path(app.__file__).resolve()),
                "--service",
                "ktalk",
                TEST_URL,
                "--close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
