"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from collections.abc import Callable
from typing import cast

from discord import TextChannel

from attubot.config import NovaConfig
from attubot.core import send_to_webhook
from attubot.logging import get_logger

logger = get_logger(__name__)


# --- Exceptions ---

class TestException(Exception):
    def __init__(self):
        self.message = 'This is a test of the DoomBot error handling system'
        super().__init__(self.message)

# --- Util Functions ---


async def _update_version(version: str):
    logger.debug(f'Applied patch for {version}')
    await NovaConfig.set('version', version)


async def error_hook_init():
    bot = NovaConfig._bot

    try:
        guild = bot.get_guild(NovaConfig.error_log[0])
        error_log = cast(TextChannel, guild.get_channel(NovaConfig.error_log[1]))

        for old in (await error_log.webhooks()):
            if old.user == bot.user:
                logger.warn(f'Deleted old webhook: {old.name}-{old.id}')
                await old.delete()

        icon = await bot.user.display_avatar.read()
        hook = await error_log.create_webhook(name=bot.user.name, avatar=icon, reason='DoomBot Error Log')

        logger.info(f'Created new webhook: {hook.name}-{hook.id}')
        NovaConfig.error_hook = await NovaConfig.set('error_hook', hook.url)

        logger.info(f'Created new webhook: {hook.name}-{hook.id}')

        try:
            raise TestException()

        except TestException as err:
            logger.warn('Sending test error to log for confirmation')
            await send_to_webhook(err)


    except Exception as err:
        logger.error(f'Failed acquiring webhook for error log: {err}')

# --- Migration Steps ---

# Version 1.8.0-pre4
async def migration_hotfix(version: str):
    # Bail out if we're past this patch
    if version != '1.8.0-pre3':
        logger.debug('Patch for 1.8.0-pre4 already applied')
        return

    # swap error log guild
    error_log = await NovaConfig.get('error_log', default=(0, 0))
    await NovaConfig.set('error_log', (NovaConfig.authorized_guilds[1], error_log[1]))

    # Bump version
    await _update_version('1.8.0-pre4')


# Version 1.8.0-pre6
async def migration_error_hooks(version: str):
    # Bail out if we're past this patch
    if version != '1.8.0-pre5':
        logger.debug('Patch for 1.8.0-pre6 already applied')
        return

    # Add ready hook to grab webhook
    logger.debug(f'Adding ready hook: {error_hook_init!s}')
    NovaConfig._ready_hooks.append(error_hook_init)

    # Bump version
    await _update_version('1.8.0-pre6')


def generic_bump(old: str, new: str):
    async def migration(version: str):
        if version == old:
            await _update_version(new)
        else:
            logger.debug(f'Patch for {new} already applied')

    return migration


# All migrations in order
migration_table: list[Callable] = [
    generic_bump(old='1.8.0-pre2', new='1.8.0-pre3'),
    migration_hotfix,
    generic_bump(old='1.8.0-pre4', new='1.8.0-pre5'),
    migration_error_hooks,
]
