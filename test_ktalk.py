import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

import launcher as app
from functools import partial
from services import SERVICES

parse_args = partial(app.parse_args, default_service="ktalk")

TEST_URL = "https://example.ktalk.ru/event/test-event"


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

        with patch.object(app, "join_guest", side_effect=join):
            total = await app.launch_guests(
                Mock(),
                parse_args([TEST_URL, "-n", "5", "--workers", "2"]),
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

        with patch.object(app, "join_guest", side_effect=join):
            task = asyncio.create_task(
                app.launch_guests(
                    Mock(),
                    parse_args([TEST_URL, "-n", "3", "--workers", "1"]),
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
            await app.join_guest(browser, parse_args([TEST_URL]), 0, contexts)
        )
        context.close.assert_awaited_once()
        self.assertEqual(contexts, [])


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


class GuestNameTests(unittest.TestCase):
    def test_random_name_is_generated_when_name_is_not_set(self):
        args = parse_args([TEST_URL, "--name-language", "ru"])
        with patch.object(app, "random_name", return_value="Иван Иванов") as generate:
            self.assertEqual(app.guest_name(args), "Иван Иванов")
        generate.assert_called_once_with("ru")

    def test_configured_name_is_shared_without_random_generation(self):
        args = parse_args([TEST_URL, "--name", "  Общий гость  "])
        with patch.object(app, "random_name") as generate:
            self.assertEqual(app.guest_name(args), "Общий гость")
        generate.assert_not_called()

    def test_empty_configured_name_is_rejected(self):
        with self.assertRaises(SystemExit):
            parse_args([TEST_URL, "--name", "   "])


class ArgumentTests(unittest.TestCase):
    def test_url_is_required(self):
        with self.assertRaises(SystemExit) as error:
            parse_args([])
        self.assertEqual(error.exception.code, 2)

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
