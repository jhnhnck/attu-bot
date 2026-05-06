"""
AttuBot - Task Scheduler
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import contextlib
import time
from collections.abc import Coroutine
from datetime import datetime

from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class TaskScheduler:
    """Async task scheduler - replaces the old JobWorker.

    Provides:
    - add_job(coro, name): fire-and-forget background tasks
    - register(task): recurring tasks that run in a loop
    - start_all(): begin all registered recurring tasks
    - stop_all(): gracefully stop all tasks
    """

    def __init__(self) -> None:
        self._jobs: set[asyncio.Task] = set()
        self._loop_tasks: set[asyncio.Task] = set()
        self._registered_tasks: list[BaseTask] = []
        self._running: bool = False

    def add_job(self, coro: Coroutine, kind: str, *parts: object) -> None:
        """Add a fire-and-forget background task.

        Args:
            coro: coroutine to run
            kind: CamelCase task kind (e.g. 'Job', 'HatchAnimation', 'PresenceUpdate')
            *parts: optional context values joined with ':' inside brackets
                    e.g. add_job(coro, 'Job', 'fix_messages', '#general')
                    produces name 'Job[fix_messages:#general]'
        """
        if parts:
            context = ':'.join(str(p) for p in parts)
            name = f'{kind}[{context}]'
        else:
            name = kind

        async def run_and_forget():
            try:
                await coro
            except Exception as e:
                logger.error(f'job {name} raised: {e}')
                await logger.send_to_webhook(e, location=f'job: {name}')

        logger.info(f'starting task: {name}')
        task = asyncio.create_task(run_and_forget(), name=name)
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    def register(self, task: BaseTask) -> None:
        """Register a recurring task (BaseTask subclass)."""
        self._registered_tasks.append(task)

    def registered_tasks(self) -> list[BaseTask]:
        """Return the currently registered task instances (for idempotence checks)."""
        return list(self._registered_tasks)

    async def start_all(self) -> None:
        """Start all registered recurring tasks."""
        if self._running:
            logger.warn('scheduler already running')
            return

        self._running = True

        for task in self._registered_tasks:
            t = asyncio.create_task(self._run_loop(task), name=f'TaskLoop[{task.name}]')
            self._loop_tasks.add(t)
            t.add_done_callback(self._loop_tasks.discard)

        logger.info(f'started [{len(self._registered_tasks)}] recurring tasks')

    async def stop_all(self) -> None:
        """Gracefully stop all tasks and wait for completion."""
        if not self._running:
            return

        logger.info('scheduler shutting down')
        self._running = False

        # cancel all loop tasks so they wake up immediately
        for t in list(self._loop_tasks):
            t.cancel()

        if self._loop_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*self._loop_tasks, return_exceptions=True), timeout=10.0)
            except TimeoutError:
                logger.warn('scheduler: timed out waiting for loop tasks to stop')

        # wait for fire-and-forget jobs to finish
        if self._jobs:
            try:
                await asyncio.wait_for(asyncio.gather(*self._jobs, return_exceptions=True), timeout=10.0)
            except TimeoutError:
                logger.warn('scheduler: timed out waiting for jobs to stop')

    async def _sleep_until(self, when: datetime, wake_event: asyncio.Event | None = None) -> None:
        """Sleep until a specific datetime, waking early if cancelled or wake_event is set."""
        delay = (when - datetime.now().astimezone()).total_seconds()
        if delay <= 0:
            return

        if wake_event is not None:
            if wake_event.is_set():
                return
            # normal expiry means the scheduled time arrived
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wake_event.wait(), timeout=delay)
        else:
            await asyncio.sleep(delay)

    async def _run_loop(self, task: BaseTask) -> None:  # noqa: PLR0912 - run_once/run_immediately/interval branches are all distinct scheduling paths
        """Internal: run a task in a loop until shutdown."""
        await task.on_start()

        if task.run_immediately:
            try:
                await task.run()
            except asyncio.CancelledError:
                await task.on_stop()
                return
            except Exception as e:
                logger.error(f'error in task {task.name} (immediate run): {e}')
                await logger.send_to_webhook(e, location=f'recurring task: {task.name} (immediate run)')

            if task.run_once:
                await task.on_stop()
                return

        while self._running:
            try:
                # dynamic scheduling: next_run() returns a specific datetime
                if task.interval is None:
                    next_dt = await task.next_run()
                    if next_dt is None:
                        logger.error(f'task {task.name} has no interval and next_run() returned None; stopping')
                        break
                    event = asyncio.Event()
                    task._wake_event = event
                    await self._sleep_until(next_dt, wake_event=event)
                    task._wake_event = None
                else:
                    await asyncio.sleep(task.interval.total_seconds())

                if not self._running:
                    break

                t0 = time.perf_counter()
                await task.run()
                elapsed_ms = (time.perf_counter() - t0) * 1000

                if task.run_once:
                    break

                if elapsed_ms >= 5000:
                    logger.warn(f'slow task: {task.name} took {elapsed_ms:.0f}ms')
                else:
                    logger.debug(f'task timing: {task.name} took {elapsed_ms:.0f}ms')

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'error in task {task.name}: {e}')
                await logger.send_to_webhook(e, location=f'recurring task: {task.name}')

        await task.on_stop()
        logger.info(f'task {task.name} stopped')

    @property
    def count(self) -> int:
        return len(self._jobs) + len(self._loop_tasks)

    @property
    def running_tasks(self) -> list[str]:
        names: list[str] = []

        for task in self._jobs:
            names.append(task.get_name())

        for task in self._loop_tasks:
            names.append(task.get_name())

        return names


# module-level singleton
scheduler = TaskScheduler()
