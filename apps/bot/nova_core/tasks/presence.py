# SPDX-License-Identifier: Apache-2.0
"""nova_core.tasks.presence | presence update task: keeps bot status in sync with egg hatch count."""

from datetime import timedelta

import discord
import structlog

from nova_core.client.core import bot, config
from nova_core.client.util import webhook_logging
from nova_core.tasks.base import BaseTask


logger = structlog.stdlib.get_logger(__name__)


class PresenceUpdateTask(BaseTask):
    """updates bot presence to reflect the total hatched egg count.

    triggered immediately on each egg hatch via scheduler.add_job() and runs
    on a 30-minute fallback schedule.
    """

    name: str = 'PresenceUpdate'
    interval: timedelta | None = timedelta(minutes=30)
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_ready()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        from nova_core.eggs.hatching import _egg_repo

        if _egg_repo is None:
            return

        try:
            count = await _egg_repo.count_hatched()
        except Exception as err:
            logger.exception('presence: failed to count hatched eggs')
            return
        try:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f'{count} eggs hatched',
                )
            )
        except Exception as err:
            logger.exception('presence: failed to update presence')


# singleton instance for registration
presence_update_task = PresenceUpdateTask()
