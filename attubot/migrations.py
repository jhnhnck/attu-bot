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

            # Bump version in MongoDB
            logger.info(f'Applied patch for {new}')
            from attubot import db
            database = db.get_db()
            await database.config.update_one(
                {'config_type': 'system'},
                {'$set': {'version': new}}
            )

        migration_table.append(wrapper)
        return wrapper
    return decorator_migration

# --- Migration Steps ---

# Version 1.8.0
@migration(old='1.8.0-pre9', new='1.8.0')
async def migration_full_release():
    pass

# Version 2.0.0
@migration(old='1.8.0', new='2.0.0')
async def migration_2_0_0():
    """Migration to schema version 2.0.0

    No structural changes needed - this is a version bump only.
    The version update is handled automatically by the @migration decorator.
    """
    logger.info('Running migration to 2.0.0')
