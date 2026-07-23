# SPDX-License-Identifier: Apache-2.0
"""nova_core.tasks.db_backup | database backup task."""

import asyncio
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from nova_core.client.core import config
from nova_core.tasks.base import BaseTask


logger = structlog.stdlib.get_logger(__name__)

_RETENTION_DAYS = 90


def _next_daily_at(time_str: str) -> datetime:
    """Return the next datetime matching the given HH:MM time string.

    If that moment is in the past (or less than 60 seconds away), advances by one day
    so the task doesn't fire immediately on startup.
    """
    h, m = (int(x) for x in time_str.split(':'))

    now = datetime.now().astimezone()
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)

    # if we're already past (or within 60s), run tomorrow
    if (candidate - now).total_seconds() < 60:
        candidate += timedelta(days=1)

    return candidate


class DatabaseBackupTask(BaseTask):
    """Daily task that runs mongodump and writes a full database backup to disk.

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

        if not shutil.which('mongodump'):
            logger.warning('mongodump not found in PATH; database backup task disabled')
            return

        self._enabled = True
        logger.info(f'database backup task enabled: path={backup_path} time={config.backup.time}')

    async def next_run(self) -> datetime | None:
        if not self._enabled:
            # return a far-future datetime to keep the loop alive but effectively idle
            return datetime.now().astimezone() + timedelta(days=365)

        return _next_daily_at(config.backup.time)

    async def run(self) -> None:
        if not self._enabled:
            return

        backup_cfg = config.backup
        db_cfg = config.database

        timestamp = datetime.now().astimezone().strftime('%Y-%m-%d_%H%M%S')
        archive_path = f'{backup_cfg.path}/{timestamp}.tar.bz2'

        logger.info(f'starting database backup to {archive_path}')

        with tempfile.TemporaryDirectory() as tmp_dir:
            dump_dir = f'{tmp_dir}/{timestamp}'

            dump_proc = await asyncio.create_subprocess_exec(
                'mongodump',
                f'--uri={db_cfg.url}',
                f'--db={db_cfg.name}',
                f'--out={dump_dir}',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await dump_proc.communicate()

            if dump_proc.returncode != 0:
                err_text = stderr.decode().strip() if stderr else '(no output)'
                logger.error(f'mongodump exited with code {dump_proc.returncode}: {err_text}')
                return

            tar_proc = await asyncio.create_subprocess_exec(
                'tar',
                '-cjf',
                archive_path,
                '-C',
                tmp_dir,
                timestamp,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            _, tar_stderr = await tar_proc.communicate()

            if tar_proc.returncode != 0:
                err_text = tar_stderr.decode().strip() if tar_stderr else '(no output)'
                logger.error(f'tar exited with code {tar_proc.returncode}: {err_text}')
                return

        logger.info(f'database backup complete: {archive_path}')
        _cleanup_old_backups(backup_cfg.path)


def _cleanup_old_backups(backup_path: str) -> None:
    """Remove .tar.bz2 backup files older than _RETENTION_DAYS days."""
    cutoff = datetime.now().astimezone() - timedelta(days=_RETENTION_DAYS)
    removed = 0
    for f in Path(backup_path).glob('*.tar.bz2'):
        mtime = datetime.fromtimestamp(f.stat().st_mtime).astimezone()
        if mtime < cutoff:
            f.unlink()
            logger.info(f'removed old backup: {f.name}')
            removed += 1
    if removed:
        logger.info(f'cleanup: removed {removed} backup(s) older than {_RETENTION_DAYS} days')


# singleton instance for registration
db_backup_task = DatabaseBackupTask()
