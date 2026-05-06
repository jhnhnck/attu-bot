"""
AttuBot - Base Task Class
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta


class BaseTask(ABC):
    """Abstract base for all recurring tasks.

    Three scheduling modes:
      - fixed interval: set `interval`; `next_run()` is unused
      - dynamic schedule: override `next_run()` to return the exact datetime for the next
        execution; `interval` should be set to None
      - run once: set `run_once = True`; `run()` is called on the first tick, then the
        task stops; `on_stop()` is called automatically after `run()` completes

    The scheduler calls `on_start()` once before entering the run loop, then either
    sleeps for `interval` or sleeps until the datetime returned by `next_run()` before
    each `run()` call. If `run_immediately` is True, `run()` is also called once right
    after `on_start()` before the first sleep.

    `on_stop()` is called once after the loop exits.
    """

    name: str = 'unnamed_task'
    interval: timedelta | None = timedelta(minutes=1)
    run_immediately: bool = False
    run_once: bool = False

    # managed by the scheduler; set during dynamic sleeps, None otherwise
    _wake_event: asyncio.Event | None = None

    def request_wake(self) -> None:
        """Interrupt a dynamic sleep so next_run() is re-evaluated immediately."""
        if self._wake_event is not None:
            self._wake_event.set()

    @abstractmethod
    async def run(self) -> None:
        """Single execution body - called once per schedule tick."""
        pass

    async def next_run(self) -> datetime | None:
        """Return the datetime for the next execution.

        Override this for dynamic scheduling. Return None to fall back to `interval`.
        Only consulted when `interval` is None or when this method is overridden.
        """
        return None

    async def on_start(self) -> None:
        """Called once before the first run. Use to await dependencies."""
        pass

    async def on_stop(self) -> None:
        """Called once after the loop exits. Use for cleanup."""
        pass
