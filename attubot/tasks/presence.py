"""
AttuBot - Presence Update Task: keeps bot status in sync with egg hatch count
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta

import discord

from attubot import bot, config
from attubot.client.util import webhook_logging
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class PresenceUpdateTask(BaseTask):
    """Updates bot presence to reflect the total hatched egg count.

    Only sets presence on hatch day. Triggered immediately on each egg hatch
    via scheduler.add_job() and runs on a 30-minute fallback schedule.
    """

    name: str = 'PresenceUpdate'
    interval: timedelta | None = timedelta(minutes=30)

    async def on_start(self) -> None:
        await config.wait_for_ready()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        from datetime import datetime

        from attubot.eggs.hatching import _egg_repo, hatch_date

        today = datetime.now(tz=config.timezone).date()
        if today < hatch_date(today.year) - timedelta(days=7):
            return

        if _egg_repo is None:
            return

        count = await _egg_repo.count_hatched()
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f'{count} eggs hatched',
        ))


# singleton instance for registration
presence_update_task = PresenceUpdateTask()
