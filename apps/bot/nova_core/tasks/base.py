# SPDX-License-Identifier: Apache-2.0
"""nova_core.tasks.base | base task class."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta


class BaseTask(ABC):
    """abstract base for all recurring tasks.

    three scheduling modes:
      - fixed interval: set `interval`; `next_run()` is unused
      - dynamic schedule: override `next_run()` to return the exact datetime for the next
        execution; `interval` should be set to None
      - run once: set `run_once = True`; `run()` is called on the first tick, then the
        task stops; `on_stop()` is called automatically after `run()` completes

    the scheduler calls `on_start()` once before entering the run loop, then either
    sleeps for `interval` or sleeps until the datetime returned by `next_run()` before
    each `run()` call. if `run_immediately` is True, `run()` is also called once right
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
        """interrupt a dynamic sleep so next_run() is re-evaluated immediately."""
        if self._wake_event is not None:
            self._wake_event.set()

    @abstractmethod
    async def run(self) -> None:
        """single execution body - called once per schedule tick."""

    async def next_run(self) -> datetime | None:
        """return the datetime for the next execution.

        override this for dynamic scheduling. return None to fall back to `interval`.
        only consulted when `interval` is None or when this method is overridden.
        """
        return None

    async def on_start(self) -> None:
        """called once before the first run. use to await dependencies."""

    async def on_stop(self) -> None:
        """called once after the loop exits. use for cleanup."""
