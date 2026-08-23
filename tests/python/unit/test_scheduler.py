# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_scheduler | unit tests for the task scheduler run loop."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from nova_core.tasks.base import BaseTask
from nova_core.tasks.scheduler import TaskScheduler


# --- helpers ---


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


# --- run_once=True, run_immediately=True ---


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


# --- run_once=True, run_immediately=False ---


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


# --- run_once=False - normal looping task ---


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


# --- add_job ---


class TestAddJob:
    async def test_add_job_runs_coroutine(self):
        """add_job wraps a coroutine in a fire-and-forget task that actually executes."""
        scheduler = TaskScheduler()
        ran = False

        async def simple_coro():
            nonlocal ran
            ran = True

        with patch('nova_core.tasks.scheduler.logger'):
            scheduler.add_job(simple_coro(), 'TestJob')
            # let the event loop process the background task
            await asyncio.sleep(0)

        assert ran

    async def test_add_job_logs_error_on_exception(self):
        """a job that raises should not propagate; the scheduler logs the error."""
        scheduler = TaskScheduler()

        async def failing_coro():
            raise RuntimeError('boom')

        with (
            patch('nova_core.tasks.scheduler.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            scheduler.add_job(failing_coro(), 'FailJob')
            await asyncio.sleep(0)

        mock_logger.error.assert_called_once()

    async def test_add_job_names_with_context_parts(self):
        """add_job(coro, 'Kind', 'a', 'b') names the asyncio task 'Kind[a:b]'."""
        scheduler = TaskScheduler()

        async def noop():
            pass

        with patch('nova_core.tasks.scheduler.logger'):
            scheduler.add_job(noop(), 'Kind', 'a', 'b')

        # the task should be in _jobs with the formatted name
        assert len(scheduler._jobs) == 1
        task = next(iter(scheduler._jobs))
        assert task.get_name() == 'Kind[a:b]'

    async def test_done_callback_discards_from_set(self):
        """after a job completes, the done callback removes it from _jobs."""
        scheduler = TaskScheduler()

        async def noop():
            pass

        with patch('nova_core.tasks.scheduler.logger'):
            scheduler.add_job(noop(), 'Ephemeral')
            assert len(scheduler._jobs) == 1
            # let the task complete and the done callback fire
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        assert len(scheduler._jobs) == 0


# --- start_all ---


class _SimpleTask(BaseTask):
    """minimal concrete task for start_all/stop_all tests."""

    name: str = 'simple_task'
    interval: timedelta | None = timedelta(seconds=60)

    async def run(self) -> None:
        pass


class TestStartAll:
    async def test_start_all_creates_loop_tasks(self):
        """registering 2 tasks and calling start_all() populates _loop_tasks."""
        scheduler = TaskScheduler()
        scheduler.register(_SimpleTask())
        scheduler.register(_SimpleTask())

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await scheduler.start_all()
            # yield so the loop tasks actually get created
            await asyncio.sleep(0)

        assert len(scheduler._loop_tasks) == 2
        assert scheduler._running is True

        # cleanup
        await scheduler.stop_all()

    async def test_start_all_double_start_warns(self):
        """calling start_all() twice logs a warning on the second call."""
        scheduler = TaskScheduler()
        scheduler.register(_SimpleTask())

        with (
            patch('asyncio.sleep', new_callable=AsyncMock),
            patch('nova_core.tasks.scheduler.logger') as mock_logger,
        ):
            await scheduler.start_all()
            await scheduler.start_all()

        mock_logger.warning.assert_called_once()

        # cleanup
        scheduler._running = False
        for t in list(scheduler._loop_tasks):
            t.cancel()
        await asyncio.gather(*scheduler._loop_tasks, return_exceptions=True)


# --- stop_all ---


class TestStopAll:
    async def test_stop_all_cancels_tasks(self):
        """after stop_all(), _running is False."""
        scheduler = TaskScheduler()
        scheduler.register(_SimpleTask())

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await scheduler.start_all()
            await asyncio.sleep(0)
            await scheduler.stop_all()

        assert scheduler._running is False

    async def test_stop_all_when_not_running_is_noop(self):
        """calling stop_all() on a fresh scheduler does not raise."""
        scheduler = TaskScheduler()
        # should complete without error
        await scheduler.stop_all()
        assert scheduler._running is False


# --- dynamic scheduling: next_run returning None ---


class _NoneNextRunTask(BaseTask):
    """task with interval=None whose next_run() always returns None."""

    name: str = 'none_next_run_task'
    interval: timedelta | None = None

    async def run(self) -> None:
        pass

    async def next_run(self):
        return None


class TestDynamicScheduling:
    async def test_next_run_returning_none_stops_task(self):
        """when next_run() returns None for an interval=None task, the loop exits and on_stop fires."""
        scheduler = _make_scheduler()
        task = _NoneNextRunTask()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()
        task.run = AsyncMock()

        with (
            patch('asyncio.sleep', new_callable=AsyncMock),
            patch('nova_core.tasks.scheduler.logger'),
        ):
            await scheduler._run_loop(task)

        task.on_stop.assert_awaited_once()
        # run() should never be called since next_run() returned None before run()
        task.run.assert_not_awaited()


# --- error in run() ---


class _FailThenSucceedTask(BaseTask):
    """task that raises on the first call then succeeds."""

    name: str = 'fail_then_succeed'
    interval: timedelta | None = timedelta(seconds=1)

    def __init__(self):
        self.call_count = 0

    async def run(self) -> None:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError('first run fails')


class TestErrorInRun:
    async def test_exception_logged_but_loop_continues(self):
        """an exception in run() is caught; the loop continues and run() is called again."""
        scheduler = _make_scheduler()
        task = _FailThenSucceedTask()
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        # stop after 2 calls
        original_run = task.run

        async def counting_run():
            await original_run()
            if task.call_count >= 2:
                scheduler._running = False

        task.run = counting_run

        with (
            patch('asyncio.sleep', new_callable=AsyncMock),
            patch('nova_core.tasks.scheduler.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await scheduler._run_loop(task)

        assert task.call_count >= 2
        mock_logger.error.assert_called_once()


# --- properties: count and running_tasks ---


class TestProperties:
    async def test_count_includes_jobs_and_loops(self):
        """count returns the total of fire-and-forget jobs plus loop tasks."""
        scheduler = TaskScheduler()
        scheduler.register(_SimpleTask())
        blocker = asyncio.Event()

        async def long_running():
            await blocker.wait()

        with (
            patch('nova_core.tasks.scheduler.logger'),
            patch.object(TaskScheduler, '_run_loop', new_callable=AsyncMock),
        ):
            await scheduler.start_all()
            await asyncio.sleep(0)
            scheduler.add_job(long_running(), 'LongJob')

        # 1 loop task + 1 job = 2
        assert scheduler.count == 2

        # cleanup - unblock the job so it finishes cleanly
        blocker.set()
        await asyncio.sleep(0)
        scheduler._running = False
        for t in list(scheduler._loop_tasks):
            t.cancel()
        await asyncio.gather(*scheduler._loop_tasks, return_exceptions=True)

    async def test_running_tasks_returns_names(self):
        """running_tasks includes names from both jobs and loop tasks."""
        scheduler = TaskScheduler()
        task = _SimpleTask()
        task.name = 'my_task'
        scheduler.register(task)
        blocker = asyncio.Event()

        async def long_running():
            await blocker.wait()

        with (
            patch('nova_core.tasks.scheduler.logger'),
            patch.object(TaskScheduler, '_run_loop', new_callable=AsyncMock),
        ):
            await scheduler.start_all()
            await asyncio.sleep(0)
            scheduler.add_job(long_running(), 'MyJob')

        names = scheduler.running_tasks
        assert 'TaskLoop[my_task]' in names
        assert 'MyJob' in names

        # cleanup - unblock the job so it finishes cleanly
        blocker.set()
        await asyncio.sleep(0)
        scheduler._running = False
        for t in list(scheduler._loop_tasks):
            t.cancel()
        await asyncio.gather(*scheduler._loop_tasks, return_exceptions=True)


# --- _sleep_until with wake_event (interruptible sleep) ---


class TestSleepUntilWake:
    async def test_pre_set_event_returns_immediately(self):
        """when the wake event is already set, _sleep_until returns without sleeping."""
        scheduler = TaskScheduler()
        event = asyncio.Event()
        event.set()

        target = datetime.now().astimezone() + timedelta(hours=1)

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await scheduler._sleep_until(target, wake_event=event)

        mock_sleep.assert_not_awaited()

    async def test_past_target_returns_immediately(self):
        """when the target is in the past, _sleep_until returns regardless of event."""
        scheduler = TaskScheduler()
        event = asyncio.Event()

        target = datetime.now().astimezone() - timedelta(seconds=10)
        await scheduler._sleep_until(target, wake_event=event)
        # should complete without blocking

    async def test_no_event_falls_back_to_sleep(self):
        """without a wake_event, _sleep_until uses plain asyncio.sleep."""
        scheduler = TaskScheduler()
        target = datetime.now().astimezone() + timedelta(seconds=5)

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await scheduler._sleep_until(target)

        mock_sleep.assert_awaited_once()
        delay = mock_sleep.call_args[0][0]
        assert 4.0 < delay <= 5.0


# --- dynamic task: request_wake() re-evaluates next_run() ---


class _WakeableDynamicTask(BaseTask):
    """dynamic task that tracks next_run() call count."""

    name: str = 'wakeable_dynamic_task'
    interval: timedelta | None = None

    def __init__(self):
        self.next_run_calls = 0
        self.run_calls = 0
        self._scheduler_ref: TaskScheduler | None = None

    async def next_run(self):
        self.next_run_calls += 1
        # first call: sleep far in the future; after wake: stop the scheduler
        if self.next_run_calls >= 2:
            self._scheduler_ref._running = False
            return datetime.now().astimezone()
        return datetime.now().astimezone() + timedelta(hours=24)

    async def run(self):
        self.run_calls += 1


class TestDynamicWake:
    async def test_request_wake_re_evaluates_next_run(self):
        """calling request_wake() during a dynamic sleep causes next_run() to be re-evaluated."""
        scheduler = _make_scheduler()
        task = _WakeableDynamicTask()
        task._scheduler_ref = scheduler
        task.on_start = AsyncMock()
        task.on_stop = AsyncMock()

        async def wake_after_brief_delay():
            # yield so the loop enters _sleep_until
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            task.request_wake()

        trigger = asyncio.create_task(wake_after_brief_delay())

        with patch('nova_core.tasks.scheduler.logger'):
            await scheduler._run_loop(task)

        await trigger

        # next_run() called at least twice: initial + after wake
        assert task.next_run_calls >= 2
        # run() called at least once (for the overdue fire after wake)
        assert task.run_calls >= 1
