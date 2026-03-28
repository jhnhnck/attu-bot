"""
AttuBot - Hatch Task: detects hatch day and loads egg extension
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta

from attubot import bot, config
from attubot.eggs.hatching import ensure_eggs_ready, hatch_date
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)

_extension = 'attubot.commands.eggs'


class HatchTask(BaseTask):
    """Hourly task that enables the egg game on hatch day.

    On hatch day (in the bot's configured timezone), reloads the egg commands extension
    if the commands aren't yet registered, syncs them, and ensures the #eggs channel exists.
    Skips command registration if already done (e.g. bot started on hatch day).
    """

    name: str = 'HatchTask'
    interval: timedelta | None = timedelta(hours=1)
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_ready()

    async def run(self) -> None:
        from datetime import datetime

        today = datetime.now(tz=config.timezone).date()

        hatch_day = hatch_date(today.year)

        if today < hatch_day:
            logger.debug(f'hatch task: before hatch day (today={today}, hatch_day={hatch_day})')
            return

        logger.info(f'hatch task: hatch day detected ({hatch_day}), ensuring egg commands are registered')

        if not any(cmd.name == 'egg' for cmd in bot.pending_application_commands):
            logger.info(f'reloading {_extension} to register egg commands for hatch day')
            bot.reload_extension(_extension)
            await bot.sync_commands()

        # trigger presence update
        from attubot.tasks.presence import presence_update_task
        from attubot.tasks.scheduler import scheduler  # local import avoids circular dep with tasks/__init__.py

        scheduler.add_job(presence_update_task.run(), 'PresenceUpdate', 'hatch_day')

        await ensure_eggs_ready()


# singleton instance for registration
hatch_task = HatchTask()
