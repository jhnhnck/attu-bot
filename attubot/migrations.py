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


# Version 2.2.0
@migration(old='2.1.0', new='2.2.0')
async def migration_backfill_years():
    """Backfill Year documents from existing YearMarker timestamps"""
    from attubot import db
    from attubot.calendar import SECONDS_PER_DAY, format_year_line, get_year_status
    from attubot.markers import YearMarker
    from attubot.repositories import YearRepository

    logger.info('Running migration to 2.2.0: backfilling year records')

    database = db.get_db()
    year_repo = YearRepository(database)
    await year_repo.init_indexes()

    for guild_id in config.authorized_guilds:
        try:
            _, current_year = get_year_status(guild_id)
        except Exception as e:
            logger.error(f'Skipping guild {guild_id} during year backfill: {e}')
            continue

        count = 0
        for yr in range(1, current_year + 1):
            start_ts = await YearMarker.timestamp(yr, guild_id)
            if start_ts is None:
                logger.warning(f'No marker for year {yr} in guild {guild_id}, skipping')
                continue

            if yr < current_year:
                end_ts = await YearMarker.timestamp(yr + 1, guild_id) or 0
            else:
                end_ts = 0

            duration = round((end_ts - start_ts) / SECONDS_PER_DAY) if end_ts > 0 else 0
            formatted = format_year_line(yr)

            await year_repo.upsert(
                guild=guild_id, year=yr, start_time=start_ts,
                end_time=end_ts, duration=duration, formatted=formatted,
            )
            count += 1

        logger.info(f'Backfilled {count} year records for guild {guild_id}')
