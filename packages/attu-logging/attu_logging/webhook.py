# SPDX-License-Identifier: Apache-2.0
"""attu_logging.webhook | error webhook reporter."""

import traceback

import structlog

from attu_logging.config import _get_webhook_url


logger = structlog.stdlib.get_logger(__name__)


def _break_at_newline(text: str, maximum: int, end: str = '...\n') -> str:
    """trim `text` to `maximum` chars, breaking only at newline boundaries.

    inlined from nova_core.client.util to keep attu_logging free of bot-package imports.
    """
    if len(text) <= maximum:
        return text

    lines = text.split('\n')
    result = ''

    for line in lines:
        potential = result + line + '\n'
        if len(potential) + len(end) > maximum:
            return (result + end)[:maximum]
        result = potential

    return (result + end)[:maximum]


async def send_to_webhook(error: Exception, location: str = '', logger_name: str = '?') -> None:
    """post a traceback for `error` to the configured discord error webhook.

    the webhook url is read at call time from attu_logging.config._webhook_url so that
    startup-vs-on_load timing is handled without re-calling configure().

    args:
        error: the exception instance to report
        location: human-readable origin string ("triggered by `user` at <link>", "job: name", etc.)
        logger_name: name of the calling logger; used in the fallback location line
    """
    tb_str = ''.join(traceback.format_exception(error))

    # log locally first so the failure is visible even if the webhook itself fails
    logger.error('error reported via webhook', exc_info=error)

    url = _get_webhook_url()
    if url is None:
        logger.warning('send_to_webhook: no webhook url configured; skipping remote report')
        return

    try:
        import aiohttp
        from discord import Webhook

        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(url, session=session)
            await webhook.send(f'**{error}**\n', username='AttuBot')

            # trim the traceback to fit discord's 2000-char limit, dropping the noisy
            # "the above exception" tail and reserving room for the codeblock fences
            padding = len('``````')
            tb_str = _break_at_newline(tb_str.split('The above exception')[0], 2000 - padding)

            await webhook.send(f'```{tb_str}```', username='AttuBot')

            end_msg = location if len(location) > 0 else f'(location not set; called from {logger_name})'
            await webhook.send(end_msg, username='AttuBot')

    except Exception as err:
        logger.error(f'issue logging error to configured webhook: {err}')
