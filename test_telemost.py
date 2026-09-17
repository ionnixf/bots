import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import telemost as app


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
                Mock(), app.parse_args(["-n", "5", "--workers", "2"]), []
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
                    Mock(), app.parse_args(["-n", "3", "--workers", "1"]), []
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
        self.assertFalse(await app.join_guest(browser, app.parse_args([]), 0, contexts))
        context.close.assert_awaited_once()
        self.assertEqual(contexts, [])


if __name__ == "__main__":
    unittest.main()
