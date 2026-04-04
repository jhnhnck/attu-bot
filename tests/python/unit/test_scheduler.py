"""
AttuBot - Task Scheduler Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Unit tests for TaskScheduler._run_loop with run_once semantics.
All tests mock asyncio.sleep to avoid real delays.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from attubot.tasks.base import BaseTask
from attubot.tasks.scheduler import TaskScheduler


# ---- helpers ----


def _make_scheduler() -> TaskScheduler:
    """Return a fresh scheduler instance with _running already set to True."""
    s = TaskScheduler()
    s._running = True
    return s


class _RunOnceImmediateTask(BaseTask):
    """run_once=True, run_immediately=True - should call run() once and stop."""

    name: str = 'test_run_once_immediate'
    interval: timedelta | None = timedelta(seconds=1)
    run_immediately: bool = True
    run_once: bool = True

    async def run(self) -> None:
        pass

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass


class _RunOnceDeferredTask(BaseTask):
    """run_once=True, run_immediately=False - should sleep once, call run(), then stop."""

    name: str = 'test_run_once_deferred'
    interval: timedelta | None = timedelta(seconds=1)
    run_immediately: bool = False
    run_once: bool = True

    async def run(self) -> None:
        pass

    async def on_start(self) -> None:
        pass

    async def on_stop(self) -> None:
        pass


# ============================================================
# run_once=True, run_immediately=True
# ============================================================


class TestRunOnceImmediate:
    async def test_run_called_exactly_once(self):
        scheduler = _make_scheduler()
        task = _RunOnceImmediateTask()
        task.run = AsyncMock()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await scheduler._run_loop(task)

        task.run.assert_awaited_once()

    async def test_on_stop_called(self):
        scheduler = _make_scheduler()
        task = _RunOnceImmediateTask()
        task.run = AsyncMock()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await scheduler._run_loop(task)

        task.on_stop.assert_awaited_once()

    async def test_exits_without_entering_while_loop(self):
        """verify asyncio.sleep is never called - the while loop is never entered."""
        scheduler = _make_scheduler()
        task = _RunOnceImmediateTask()
        task.run = AsyncMock()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await scheduler._run_loop(task)

        mock_sleep.assert_not_awaited()


# ============================================================
# run_once=True, run_immediately=False
# ============================================================


class TestRunOnceDeferred:
    async def test_run_called_exactly_once(self):
        scheduler = _make_scheduler()
        task = _RunOnceDeferredTask()
        task.run = AsyncMock()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await scheduler._run_loop(task)

        task.run.assert_awaited_once()

    async def test_on_stop_called(self):
        scheduler = _make_scheduler()
        task = _RunOnceDeferredTask()
        task.run = AsyncMock()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await scheduler._run_loop(task)

        task.on_stop.assert_awaited_once()

    async def test_sleep_called_once_before_run(self):
        """one sleep (the interval wait) before the single run() call."""
        scheduler = _make_scheduler()
        task = _RunOnceDeferredTask()
        task.run = AsyncMock()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await scheduler._run_loop(task)

        mock_sleep.assert_awaited_once_with(1.0)


# ============================================================
# run_once=False - normal looping task
# ============================================================


class TestNormalLoopTask:
    async def test_run_called_multiple_times(self):
        """a non-run_once task should loop and call run() more than once."""
        scheduler = _make_scheduler()
        task = _RunOnceDeferredTask()
        # override run_once so it loops
        task.run_once = False
        call_count = 0

        async def counting_run():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                scheduler._running = False

        task.run = counting_run
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await scheduler._run_loop(task)

        assert call_count >= 3
