"""
AttuBot - Hatch Task: detects hatch day and loads egg extension
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta

from attubot import config
from attubot.eggs.hatching import ensure_eggs_ready, hatch_date
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class HatchTask(BaseTask):
    """Hourly task that activates the egg game on hatch day and runs per-season setup.

    On hatch day, sets eggs_active = True on the primary guild config (persisted to MongoDB)
    if not already set. Once active, ensures the #eggs channel exists and triggers a
    presence update. The flag stays set until manually cleared, allowing the game to
    remain active beyond the seasonal window.
    """

    name: str = 'HatchTask'
    interval: timedelta | None = timedelta(hours=1)
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_ready()

    async def run(self) -> None:
        from datetime import datetime

        today = datetime.now(tz=config.timezone).date()
        guild_cfg = config.primary()

        # auto-activate on hatch day if not already enabled
        if not guild_cfg.eggs_active and today >= hatch_date(today.year):
            logger.info(f'hatch task: activating eggs for hatch day {hatch_date(today.year)}')
            guild_cfg.eggs_active = True
            await config.config_repo.update_guild_field(guild_cfg.id, 'eggs_active', True)

        if not guild_cfg.eggs_active:
            logger.debug(f'hatch task: eggs not active (today={today})')
            return

        # trigger presence update
        from attubot.tasks.presence import presence_update_task
        from attubot.tasks.scheduler import scheduler  # local import avoids circular dep with tasks/__init__.py

        scheduler.add_job(presence_update_task.run(), 'PresenceUpdate', 'hatch_day')

        await ensure_eggs_ready()


# singleton instance for registration
hatch_task = HatchTask()
