"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from collections.abc import Callable

from attubot.config import NovaConfig
from attubot.logging import get_logger

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
        from attubot.calendar import error_hook_refresh

        await error_hook_refresh(NovaConfig._bot)

    # Add ready hook to grab webhook
    logger.debug(f'Adding ready hook: {error_hook_init!s}')
    NovaConfig._ready_hooks.append(error_hook_init)


# Version 1.8.0-pre7
@migration(old='1.8.0-pre6', new='1.8.0-pre7')
async def migration_named_guilds():
    NovaConfig.primary_guild = await NovaConfig.set('primary_guild', NovaConfig.primary_guild)
