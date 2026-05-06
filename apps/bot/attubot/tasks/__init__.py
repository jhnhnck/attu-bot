"""
AttuBot - Tasks Package
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.logging import get_logger
from attubot.tasks.base import BaseTask
from attubot.tasks.db_backup import DatabaseBackupTask, db_backup_task
from attubot.tasks.egg_cleanup import EggCleanupTask, egg_cleanup_task
from attubot.tasks.error_hook import ErrorHookTask, error_hook_refresh, error_hook_task
from attubot.tasks.logo_update import LogoUpdateTask, logo_update_task
from attubot.tasks.message_backfill import MessageBackfillTask, message_backfill_task
from attubot.tasks.nova_year import NovaYearTask, nova_year_task
from attubot.tasks.presence import PresenceUpdateTask, presence_update_task
from attubot.tasks.reload_watcher import ReloadWatcherTask, reload_watcher_task
from attubot.tasks.reminder import ReminderTask, reminder_task
from attubot.tasks.scheduler import TaskScheduler, scheduler


logger = get_logger(__name__)


def register_bot_tasks(s: TaskScheduler) -> None:
    """register all bot-side recurring tasks on the given scheduler.

    called once from the bot startup path; not called by the ingestor (which has
    its own task set). registering at module-import time would duplicate every
    bot task into the ingestor process, since both processes share this package.
    idempotent: tasks already registered are skipped.
    """
    bot_tasks = (
        nova_year_task,
        logo_update_task,
        error_hook_task,
        reload_watcher_task,
        db_backup_task,
        message_backfill_task,
        egg_cleanup_task,
        presence_update_task,
        reminder_task,
    )
    registered = set(s.registered_tasks())
    for task in bot_tasks:
        if task not in registered:
            s.register(task)


__all__ = [
    'BaseTask',
    'DatabaseBackupTask',
    'EggCleanupTask',
    'ErrorHookTask',
    'LogoUpdateTask',
    'MessageBackfillTask',
    'NovaYearTask',
    'PresenceUpdateTask',
    'ReloadWatcherTask',
    'ReminderTask',
    'TaskScheduler',
    'db_backup_task',
    'egg_cleanup_task',
    'error_hook_refresh',
    'error_hook_task',
    'logo_update_task',
    'message_backfill_task',
    'nova_year_task',
    'presence_update_task',
    'register_bot_tasks',
    'reload_watcher_task',
    'reminder_task',
    'scheduler',
]
