"""
AttuBot - Task Scheduler
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
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

    def add_job(self, coro: Coroutine, name: str | None = None) -> None:
        """Add a fire-and-forget background task."""
        if not name:
            from uuid import uuid4

            name = f'Task[{uuid4().hex[:16]}]'

        async def run_and_forget():
            try:
                await coro
            except Exception as e:
                logger.error(f'Job {name} raised: {e}')

        logger.info(f'Starting task: {name}')
        task = asyncio.create_task(run_and_forget(), name=name)
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    def register(self, task: BaseTask) -> None:
        """Register a recurring task (BaseTask subclass)."""
        self._registered_tasks.append(task)

    async def start_all(self) -> None:
        """Start all registered recurring tasks."""
        if self._running:
            logger.warn('Scheduler already running')
            return

        self._running = True

        for task in self._registered_tasks:
            t = asyncio.create_task(self._run_loop(task), name=f'TaskLoop[{task.name}]')
            self._loop_tasks.add(t)
            t.add_done_callback(self._loop_tasks.discard)

        logger.info(f'Started {len(self._registered_tasks)} recurring tasks')

    async def stop_all(self) -> None:
        """Gracefully stop all tasks and wait for completion."""
        if not self._running:
            return

        logger.info('Scheduler shutting down')
        self._running = False

        # cancel all loop tasks so they wake up immediately
        for t in list(self._loop_tasks):
            t.cancel()

        if self._loop_tasks:
            await asyncio.gather(*self._loop_tasks, return_exceptions=True)

        # wait for fire-and-forget jobs to finish
        if self._jobs:
            await asyncio.gather(*self._jobs, return_exceptions=True)

    async def _sleep_until(self, when: datetime) -> None:
        """Sleep until a specific datetime, waking early if cancelled."""
        delay = (when - datetime.now().astimezone()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

    async def _run_loop(self, task: BaseTask) -> None:
        """Internal: run a task in a loop until shutdown."""
        await task.on_start()

        if task.run_immediately:
            try:
                await task.run()
            except asyncio.CancelledError:
                await task.on_stop()
                return
            except Exception as e:
                logger.error(f'Error in task {task.name} (immediate run): {e}')

        while self._running:
            try:
                # dynamic scheduling: next_run() returns a specific datetime
                if task.interval is None:
                    next_dt = await task.next_run()
                    if next_dt is None:
                        logger.error(f'Task {task.name} has no interval and next_run() returned None; stopping')
                        break
                    await self._sleep_until(next_dt)
                else:
                    await asyncio.sleep(task.interval.total_seconds())

                if not self._running:
                    break

                await task.run()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'Error in task {task.name}: {e}')

        await task.on_stop()
        logger.info(f'Task {task.name} stopped')

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
