# SPDX-License-Identifier: Apache-2.0
"""doom_bot.tasks.presence | presence update task: keeps bot status in sync with egg hatch count."""

from datetime import timedelta

import discord

from doom_bot import bot, config
from doom_bot.client.util import webhook_logging
from doom_bot.logging import get_logger
from doom_bot.tasks.base import BaseTask


logger = get_logger(__name__)


class PresenceUpdateTask(BaseTask):
    """Updates bot presence to reflect the total hatched egg count.

    Only sets presence on hatch day. Triggered immediately on each egg hatch
    via scheduler.add_job() and runs on a 30-minute fallback schedule.
    """

    name: str = 'PresenceUpdate'
    interval: timedelta | None = timedelta(minutes=30)
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_ready()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        from doom_bot.eggs.hatching import _egg_repo

        if _egg_repo is None:
            return

        try:
            count = await _egg_repo.count_hatched()
        except Exception as err:
            logger.error(f'presence: failed to count hatched eggs: {err}')
            return
        try:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f'{count} eggs hatched',
                )
            )
        except Exception as err:
            logger.error(f'presence: failed to update presence: {err}')


# singleton instance for registration
presence_update_task = PresenceUpdateTask()
