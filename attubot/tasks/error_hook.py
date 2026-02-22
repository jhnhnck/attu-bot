"""
AttuBot - Error Hook Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta
from typing import cast

from discord import TextChannel

from attubot import bot, config
from attubot.logging import get_logger
from attubot.logo import generate_png
from attubot.tasks.base import BaseTask
from attubot.util import webhook_logging

logger = get_logger(__name__)


class ErrorHookTask(BaseTask):
    """Ensures the error webhook exists and refreshes it if needed.

    Runs once at startup (via run_immediately) and then hourly to ensure the webhook is valid.
    """

    name: str = 'ErrorHookRefresh'
    interval = timedelta(hours=1)
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_load()
        await bot.wait_until_ready()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        """Ensure error webhook exists."""
        if config.test_mode:
            logger.debug('Application in test mode; skipping error hook refresh')
            return

        try:
            guild = bot.get_guild(config.error_log[0])
            error_log = cast(TextChannel, guild.get_channel(config.error_log[1]))

            webhooks = await error_log.webhooks()
            webhook_urls = [hook.url for hook in webhooks]

            # cleanup old urls
            for old in webhooks:
                if old.user == bot.user and old.url != config.error_hook:
                    logger.warn(f'Deleted old webhook: {old.name}-{old.id}')
                    await old.delete()

            if config.error_hook in webhook_urls:
                logger.debug('Existing error hook found; skipping refresh')
                return

            icon = await generate_png(45, '#ff4941')
            hook = await error_log.create_webhook(name=bot.user.name, avatar=icon, reason='DoomBot Error Log')

            logger.info(f'Created new webhook: {hook.name}-{hook.id}')
            config.error_hook = hook.url
            await config.config_repo.update_system_field('error_hook', hook.url)

        except Exception as err:
            logger.error(f'Failed acquiring new webhook for error log: {err}')


# singleton for backwards compatibility - standalone function too
error_hook_task = ErrorHookTask()


# backwards compatible standalone function
async def error_hook_refresh() -> None:
    """Standalone function for running error hook refresh (used by core.py)."""
    task = ErrorHookTask()
    await task.run()
