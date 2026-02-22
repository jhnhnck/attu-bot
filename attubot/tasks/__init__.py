"""
AttuBot - Tasks Package
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.logging import get_logger
from attubot.tasks.base import BaseTask
from attubot.tasks.error_hook import ErrorHookTask, error_hook_refresh, error_hook_task
from attubot.tasks.logo_update import LogoUpdateTask, logo_update_task
from attubot.tasks.nova_year import NovaYearTask, nova_year_task
from attubot.tasks.reload_watcher import ReloadWatcherTask, reload_watcher_task
from attubot.tasks.scheduler import TaskScheduler, scheduler

logger = get_logger(__name__)

# register all tasks
scheduler.register(nova_year_task)
scheduler.register(logo_update_task)
scheduler.register(error_hook_task)
scheduler.register(reload_watcher_task)


__all__ = [
    'BaseTask',
    'ErrorHookTask',
    'LogoUpdateTask',
    'NovaYearTask',
    'ReloadWatcherTask',
    'TaskScheduler',
    'error_hook_refresh',
    'error_hook_task',
    'logo_update_task',
    'nova_year_task',
    'reload_watcher_task',
    'scheduler',
]
