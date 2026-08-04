# SPDX-License-Identifier: Apache-2.0
"""nova_core.tasks | tasks package."""

import structlog

from nova_core.tasks.base import BaseTask
from nova_core.tasks.db_backup import DatabaseBackupTask, db_backup_task
from nova_core.tasks.egg_cleanup import EggCleanupTask, egg_cleanup_task
from nova_core.tasks.error_hook import ErrorHookTask, error_hook_refresh, error_hook_task
from nova_core.tasks.logo_update import LogoUpdateTask, logo_update_task
from nova_core.tasks.message_backfill import MessageBackfillTask, message_backfill_task
from nova_core.tasks.nova_year import NovaYearTask, nova_year_task
from nova_core.tasks.presence import PresenceUpdateTask, presence_update_task
from nova_core.tasks.reload_watcher import ReloadWatcherTask, reload_watcher_task
from nova_core.tasks.reminder import ReminderTask, reminder_task
from nova_core.tasks.scheduler import TaskScheduler, scheduler


logger = structlog.stdlib.get_logger(__name__)


def register_bot_tasks(s: TaskScheduler) -> None:
    """register all bot-side recurring tasks on the given scheduler.

    called once from the bot startup path; not called by the ingestor (which has
    its own task set). registering at module-import time would duplicate every
    bot task into the ingestor process, since both processes share this package.
    idempotent: tasks already registered are skipped.
    """
    # local import: nova_core.ccboard.manager pulls in client.starboard helpers via
    # the builder, which back-imports nova_core.tasks. eager import here would
    # collide with that load order at first import. moving it inside the function
    # defers manager construction until startup, after the package graph is settled.
    # the auditor task lives in the same package and follows the same lazy-import rule.
    from nova_core.ccboard.auditor import auditor_task as ccboard_auditor_task
    from nova_core.ccboard.manager import manager_task as ccboard_manager_task

    # db_backup_task, error_hook_task, and reload_watcher_task are now registered by
    # load_base(BASE_PACKAGE) in _do_ready_init(); removed here to avoid duplicate registration
    bot_tasks = (
        nova_year_task,
        logo_update_task,
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
