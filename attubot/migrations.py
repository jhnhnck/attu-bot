"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio

from attubot.config import NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)

async def _update_version(version: str):
    logger.debug(f'Applied patch for {version}')
    await NovaConfig.set('version', version)


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


def generic_bump(old: str, new: str):
    async def migration(version: str):
        if version == old:
            await _update_version(new)
        else:
            logger.debug(f'Patch for {new} already applied')

    return migration


# All migrations in order
migration_table = [
    generic_bump(old='1.8.0-pre2', new='1.8.0-pre3'),
    migration_hotfix,
    generic_bump(old='1.8.0-pre4', new='1.8.0-pre5'),
]
