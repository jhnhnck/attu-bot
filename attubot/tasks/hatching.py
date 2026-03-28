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

_EXTENSION = 'attubot.eggs.commands'


class HatchTask(BaseTask):
    """Hourly task that enables the egg game on hatch day.

    On hatch day (in the bot's configured timezone), loads the egg commands extension
    and ensures the #eggs channel exists with its intro message.
    Skips setup if the extension is already loaded (e.g. after a restart mid-event).
    """

    name: str = 'HatchTask'
    interval: timedelta = timedelta(hours=1)
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_ready()

    async def run(self) -> None:
        from datetime import datetime
        today = datetime.now(tz=config.timezone).date()

        hatch_day = hatch_date(today.year)

        if today != hatch_day:
            logger.debug(f'hatch task: not hatch day yet (today={today}, hatch_day={hatch_day})')
            return

        logger.info(f'hatch task: hatch day detected ({hatch_day}), ensuring egg extension is loaded')

        if _EXTENSION not in bot.extensions:
            logger.info(f'loading extension {_EXTENSION}')
            bot.load_extension(_EXTENSION)
            # sync commands so the new slash commands are registered
            await bot.sync_commands()

        await ensure_eggs_ready()


# singleton instance for registration
hatch_task = HatchTask()
