"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio

from attubot.config import Config, NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)

async def _update_version(version: str):
    logger.debug(f'Applied patch for {version}')
    await NovaConfig.set('version', version)


# Version 1.8.0-pre2
async def import_migration(version: str):
    # Bail out if we're past this patch
    if version != '1.8.0-pre':
        logger.debug('Patch for 1.8.0-pre2 already applied')
        return

    # global vars
    await asyncio.gather(
        NovaConfig.set('error_log', (Config.attu_guild, Config.error_log_channel)),
    )

    # migrate existing to all guilds
    for guild in NovaConfig.authorized_guilds:
        logger.info(f'Migrating {guild} to database')

        await asyncio.gather(
            NovaConfig.set('channels.activity', Config.activity_channel, guild=guild),
            NovaConfig.set('channels.year_vc', Config.year_vc, guild=guild),
            NovaConfig.set('channels.announcements', Config.announce_channel, guild=guild),
            NovaConfig.set('channels.year_links', Config.year_link_thread, guild=guild),
            NovaConfig.set('channels.meta_chat', Config.meta_chat_channel, guild=guild),
            NovaConfig.set('channels.lore_channels', Config.lore_channels, guild=guild),
            NovaConfig.set('epoch.time', Config.epoch_time, guild=guild),
            NovaConfig.set('epoch.year', Config.epoch_year, guild=guild),
            NovaConfig.set('epoch.length', Config.epoch_length, guild=guild),
            NovaConfig.set('epoch.paused', Config.time_paused, guild=guild),
            NovaConfig.set('epoch.rollover_time', Config._raw['epoch']['rollover_time'], guild=guild),
            NovaConfig.set('roles.announcements', Config.announce_role, guild=guild),
            NovaConfig.set('users.markers', Config.users.markers, guild=guild),
            NovaConfig.delete('markers', guild=guild),
        )

    # Bump version
    await _update_version('1.8.0-pre2')


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
    import_migration,
    generic_bump(old='1.8.0-pre2', new='1.8.0-pre3'),
    migration_hotfix,
    generic_bump(old='1.8.0-pre4', new='1.8.0-pre5'),
]
