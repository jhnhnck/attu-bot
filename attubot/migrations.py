"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from collections.abc import Callable

from attubot import config
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
            await config.set('version', new)

        migration_table.append(wrapper)
        return wrapper
    return decorator_migration

# --- Migration Steps ---

# Version 1.8.0
@migration(old='1.8.0-pre9', new='1.8.0')
async def migration_full_release():
    pass
