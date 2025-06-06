"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from collections.abc import Callable

from attubot.config import NovaConfig
from attubot.logging import get_logger
from attubot.util import create_task

logger = get_logger(__name__)

migration_table: list[Callable] = []

# --- Decorator ---

def migration(old: str, new: str) -> Callable:
    def decorator_migration(func: Callable) -> Callable:
        async def wrapper(version: str):
            # Bail out if we're past this patch
            if version != old:
                logger.debug(f'Patch for {new} already applied')
                return

            # call migrator
            await func()

            # Bump version
            logger.debug(f'Applied patch for {new}')
            await NovaConfig.set('version', new)

        migration_table.append(wrapper)
        return wrapper
    return decorator_migration

# --- Migration Steps ---

# Version 1.8.0-pre5
@migration(old='1.8.0-pre4', new='1.8.0-pre5')
async def migration_pre4():
    pass


# Version 1.8.0-pre6
@migration(old='1.8.0-pre5', new='1.8.0-pre6')
async def migration_error_hooks():

    async def error_hook_init():
        from attubot.tasks import error_hook_refresh

        await NovaConfig.wait_for_ready()
        await error_hook_refresh(NovaConfig._bot)

    # Add ready hook to grab webhook
    create_task(error_hook_init())
    logger.debug(f'Created future task for {error_hook_init!s}')


# Version 1.8.0-pre7
@migration(old='1.8.0-pre6', new='1.8.0-pre7')
async def migration_named_guilds():
    NovaConfig.primary_guild = await NovaConfig.set('primary_guild', NovaConfig.primary_guild)


# Version 1.8.0-pre8
@migration(old='1.8.0-pre7', new='1.8.0-pre8')
async def migration_markers_move():

    async def migrate_guild_markers():
        from attubot.markers import YearMarker

        await NovaConfig.wait_for_ready()

        logger.debug(f'Updating markers from 0 -> {NovaConfig.primary_guild}')
        primary_guild = int(NovaConfig.primary_guild)
        await YearMarker.raw(f'UPDATE yearmarker SET channel = {primary_guild} WHERE channel = 0;')  # noqa: S608

    # Create a task so this executes after ready
    create_task(migrate_guild_markers())
    logger.debug(f'Created future task for {migrate_guild_markers!s}')


# Version 1.8.0-pre9
@migration(old='1.8.0-pre8', new='1.8.0-pre9')
async def migration_themes():
    await NovaConfig.set('theme.rotation', 0.0)
    await NovaConfig.set('theme.max_rate', 0.5)
    await NovaConfig.set('theme.bot_color', '#ff7f50')
    await NovaConfig.set('theme.guild_color', '#ffffff')


# Version 1.8.0
@migration(old='1.8.0-pre9', new='1.8.0')
async def migration_full_release():
    pass
