"""
AttuBot - Database Backup Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import shutil
from datetime import datetime, timedelta

from attubot import config
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask

logger = get_logger(__name__)

# weekday name -> isoweekday (monday=1 ... sunday=7)
_WEEKDAYS = {
    'monday': 1,
    'tuesday': 2,
    'wednesday': 3,
    'thursday': 4,
    'friday': 5,
    'saturday': 6,
    'sunday': 7,
}


def _next_weekday_at(day_name: str, time_str: str) -> datetime:
    """Return the next datetime matching the given weekday and HH:MM time string.

    If that moment is in the past (or less than 60 seconds away), advances by one week
    so the task doesn't fire immediately on startup.
    """
    target_isoweekday = _WEEKDAYS[day_name.lower()]
    h, m = (int(x) for x in time_str.split(':'))

    now = datetime.now().astimezone()
    # start from today at the target time
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)

    # advance forward by whole days until we land on the right weekday
    days_ahead = (target_isoweekday - candidate.isoweekday()) % 7
    candidate += timedelta(days=days_ahead)

    # if we're already past (or within 60s), jump a full week
    if (candidate - now).total_seconds() < 60:
        candidate += timedelta(weeks=1)

    return candidate


class DatabaseBackupTask(BaseTask):
    """Weekly task that runs mongodump and writes a full database backup to disk.

    Disabled (no-op) when config.backup.path is empty or mongodump is not found.
    """

    name: str = 'DatabaseBackupTask'
    interval: timedelta | None = None  # dynamic scheduling via next_run()

    def __init__(self):
        self._enabled: bool = False

    async def on_start(self) -> None:
        await config.wait_for_init()

        backup_path = config.backup.path
        if not backup_path:
            logger.info('backup path not configured; database backup task disabled')
            return

        if shutil.which('mongodump') is None:
            logger.warn('mongodump not found in PATH; database backup task disabled')
            return

        self._enabled = True
        logger.info(f'database backup task enabled: path={backup_path} day={config.backup.day} time={config.backup.time}')

    async def next_run(self) -> datetime | None:
        if not self._enabled:
            # return a far-future datetime to keep the loop alive but effectively idle
            return datetime.now().astimezone() + timedelta(days=365)

        return _next_weekday_at(config.backup.day, config.backup.time)

    async def run(self) -> None:
        if not self._enabled:
            return

        backup_cfg = config.backup
        db_cfg = config.database

        timestamp = datetime.now().astimezone().strftime('%Y-%m-%d_%H%M%S')
        out_dir = f'{backup_cfg.path}/{timestamp}'

        logger.info(f'starting database backup to {out_dir}')

        proc = await asyncio.create_subprocess_exec(
            'mongodump',
            f'--uri={db_cfg.url}',
            f'--db={db_cfg.name}',
            f'--out={out_dir}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info(f'database backup complete: {out_dir}')
        else:
            err_text = stderr.decode().strip() if stderr else '(no output)'
            logger.error(f'mongodump exited with code {proc.returncode}: {err_text}')


# singleton instance for registration
db_backup_task = DatabaseBackupTask()
