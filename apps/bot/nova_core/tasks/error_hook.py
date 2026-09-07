# SPDX-License-Identifier: Apache-2.0
"""nova_core.tasks.error_hook | error hook task."""

from datetime import timedelta
from typing import cast

import structlog
from discord import TextChannel

from nova_core.client.core import bot, config
from nova_core.client.logo import generate_png
from nova_core.client.util import webhook_logging
from nova_core.tasks.base import BaseTask


logger = structlog.stdlib.get_logger(__name__)


class ErrorHookTask(BaseTask):
    """ensures the error webhook exists and refreshes it if needed.

    runs once at startup (via run_immediately) and then hourly to ensure the webhook is valid.
    """

    name: str = 'ErrorHookRefresh'
    interval = timedelta(hours=1)
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_load()
        await bot.wait_until_ready()

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        """ensure error webhook exists."""
        if config.test_mode:
            logger.debug('application in test mode; skipping error hook refresh')
            return

        try:
            guild = bot.get_guild(config.error_log[0])
            error_log = cast(TextChannel, guild.get_channel(config.error_log[1]))

            webhooks = await error_log.webhooks()
            webhook_urls = [hook.url for hook in webhooks]

            for old in webhooks:
                if old.user == bot.user and old.url != config.error_hook:
                    try:
                        await old.delete()
                        logger.warning(f'deleted old webhook: {old.name}-{old.id}')
                    except Exception as del_err:
                        logger.warning(f'failed to delete old webhook {old.name}-{old.id}: {del_err}')

            if config.error_hook in webhook_urls:
                logger.debug('existing error hook found; skipping refresh')
                return

            try:
                icon = await generate_png(45, '#ff4941')
                hook = await error_log.create_webhook(name=bot.user.name, avatar=icon, reason=f'{config.bot.name} Error Log')
                logger.info(f'created new webhook: {hook.name}-{hook.id}')
                config.error_hook = hook.url
                await config.config_repo.update_system_field('error_hook', hook.url)
            except Exception as create_err:
                logger.exception('failed to create new webhook for error log')

        except Exception as err:
            logger.exception('failed acquiring new webhook for error log')


# singleton instance for registration
error_hook_task = ErrorHookTask()


# backwards-compat standalone wrapper
async def error_hook_refresh() -> None:
    task = ErrorHookTask()
    await task.run()
