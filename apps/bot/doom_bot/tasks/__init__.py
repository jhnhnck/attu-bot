# SPDX-License-Identifier: Apache-2.0
"""doom_bot.tasks | tasks package."""

from doom_bot.logging import get_logger
from doom_bot.tasks.base import BaseTask
from doom_bot.tasks.db_backup import DatabaseBackupTask, db_backup_task
from doom_bot.tasks.egg_cleanup import EggCleanupTask, egg_cleanup_task
from doom_bot.tasks.error_hook import ErrorHookTask, error_hook_refresh, error_hook_task
from doom_bot.tasks.logo_update import LogoUpdateTask, logo_update_task
from doom_bot.tasks.message_backfill import MessageBackfillTask, message_backfill_task
from doom_bot.tasks.nova_year import NovaYearTask, nova_year_task
from doom_bot.tasks.presence import PresenceUpdateTask, presence_update_task
from doom_bot.tasks.reload_watcher import ReloadWatcherTask, reload_watcher_task
from doom_bot.tasks.reminder import ReminderTask, reminder_task
from doom_bot.tasks.scheduler import TaskScheduler, scheduler


logger = get_logger(__name__)


def register_bot_tasks(s: TaskScheduler) -> None:
    """register all bot-side recurring tasks on the given scheduler.

    called once from the bot startup path; not called by the ingestor (which has
    its own task set). registering at module-import time would duplicate every
    bot task into the ingestor process, since both processes share this package.
    idempotent: tasks already registered are skipped.
    """
    # local import: doom_bot.ccboard.manager pulls in client.starboard helpers via
    # the builder, which back-imports doom_bot.tasks. eager import here would
    # collide with that load order at first import. moving it inside the function
    # defers manager construction until startup, after the package graph is settled.
    # the auditor task lives in the same package and follows the same lazy-import rule.
    from doom_bot.ccboard.auditor import auditor_task as ccboard_auditor_task
    from doom_bot.ccboard.manager import manager_task as ccboard_manager_task

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
        ccboard_manager_task,
        ccboard_auditor_task,
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
