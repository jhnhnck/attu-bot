# SPDX-License-Identifier: Apache-2.0
"""doom_bot.webhook | error webhook reporter."""

import traceback

from doom_bot.logging import get_logger


logger = get_logger(__name__)


async def send_to_webhook(error: Exception, location: str = '', logger_name: str = '?') -> None:
    """post a traceback for `error` to the configured discord error webhook.

    args:
        error: the exception instance to report
        location: human-readable origin string ("triggered by `user` at <link>", "job: name", etc.)
        logger_name: name of the calling logger; used in the fallback location line
    """
    tb_str = ''.join(traceback.format_exception(error))

    # log locally first so the failure is visible even if the webhook itself fails
    logger.error(f'{error!s}\n{tb_str}')

    try:
        import aiohttp
        from discord import Webhook

        from doom_bot import config
        from doom_bot.client.util import break_at_newline

        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(config.error_hook, session=session)
            await webhook.send(f'**{error}**\n', username='DoomBot')

            # trim the traceback to fit discord's 2000-char limit, dropping the noisy
            # "the above exception" tail and reserving room for the codeblock fences
            padding = len('``````')
            tb_str = break_at_newline(tb_str.split('The above exception')[0], 2000 - padding)

            await webhook.send(f'```{tb_str}```', username='DoomBot')

            end_msg = location if len(location) > 0 else f'(location not set; called from {logger_name})'
            await webhook.send(end_msg, username='DoomBot')

    except Exception as err:
        logger.error(f'issue logging error to configured webhook: {err}')
