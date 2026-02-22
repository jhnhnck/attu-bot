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


class MigrationError(Exception):
    """Raised when a migration fails; signals the bot should not continue initializing."""


# --- Backup / Restore Helpers ---


async def _backup_collection(db, name: str) -> list[dict]:
    """Snapshot all documents in a collection for rollback purposes."""
    docs = await db[name].find({}).to_list(length=None)
    return [dict(doc) for doc in docs]


async def _restore_collection(db, name: str, backup: list[dict]):
    """Restore a collection from a snapshot, replacing all current contents."""
    await db[name].delete_many({})
    if backup:
        clean = [{k: v for k, v in doc.items() if k != '_id'} for doc in backup]
        await db[name].insert_many(clean)


# --- Decorator ---


def migration(old: str, new: str) -> Callable:
    def decorator_migration(func: Callable) -> Callable:
        async def wrapper(version: str):
            # Bail out if we're past this patch
            if version != old:
                logger.debug(f'Patch for {new} already applied')
                return

            # call migrator — do NOT bump version if it fails
            try:
                await func()
            except Exception as e:
                logger.error(f'Migration to {new} FAILED: {e}')
                raise MigrationError(f'Migration to {new} failed') from e

            # Bump version in MongoDB
            logger.info(f'Applied patch for {new}')
            from attubot import db

            database = db.get_db()
            await database.global_config.update_one(
                {'config_type': 'system'},
                {'$set': {'version': new}},
            )

        migration_table.append(wrapper)
        return wrapper

    return decorator_migration


# --- Migration Steps ---


# Bootstrap: fresh database with no prior version
@migration(old='0.0.0', new='1.8.0-pre9')
async def migration_bootstrap():
    """Bootstrap migration for fresh databases"""
    pass


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


# Version 2.1.0
@migration(old='2.0.0', new='2.1.0')
async def migration_2_1_0():
    """Migration to schema version 2.1.0

    No structural changes needed - this is a version bump only.
    The version update is handled automatically by the @migration decorator.
    """
    logger.info('Running migration to 2.1.0')


# Version 2.2.0
@migration(old='2.1.0', new='2.2.0')
async def migration_2_2_0():
    """Migration to schema version 2.2.0

    No structural changes needed - this is a version bump only.
    The version update is handled automatically by the @migration decorator.
    """
    logger.info('Running migration to 2.2.0')


# Version 2.2.1
@migration(old='2.2.0', new='2.2.1')
async def migration_backfill_years():
    """Backfill Year documents from existing YearMarker timestamps"""
    from attubot import db
    from attubot.calendar import SECONDS_PER_DAY, format_year_line, get_year_status
    from attubot.database.repositories import YearRepository
    from attubot.markers import YearMarker

    logger.info('Running migration to 2.2.1: backfilling year records')

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
                logger.warn(f'No marker for year {yr} in guild {guild_id}, skipping')
                continue

            end_ts = await YearMarker.timestamp(yr + 1, guild_id) or 0 if yr < current_year else 0
            duration = round((end_ts - start_ts) / SECONDS_PER_DAY) if end_ts > 0 else 0
            formatted = format_year_line(yr)

            await year_repo.upsert(
                guild=guild_id,
                year=yr,
                start_time=start_ts,
                end_time=end_ts,
                duration=duration,
                formatted=formatted,
            )
            count += 1

        logger.info(f'Backfilled {count} year records for guild {guild_id}')


# Version 2.2.1
@migration(old='2.2.1', new='2.2.3')
async def migration_2_2_1():
    pass


# Version 2.2.2
@migration(old='2.2.3', new='2.2.4')
async def migration_fix_year_data():
    """Fix year data: strip markdown headings, regenerate missing symbols, finalize past years"""
    from attubot import db
    from attubot.calendar import SECONDS_PER_DAY, format_year_line, get_year_status
    from attubot.database.repositories import YearRepository

    logger.info('Running migration to 2.2.4: fixing year data')

    database = db.get_db()
    year_repo = YearRepository(database)

    for guild_id in config.authorized_guilds:
        try:
            _, current_year = get_year_status(guild_id)
        except Exception as e:
            logger.error(f'Skipping guild {guild_id} during year fix: {e}')
            continue

        all_years = await year_repo.all_for_guild(guild_id)
        years_by_num = {y.year: y for y in all_years}

        for year_doc in all_years:
            updates = {}

            # Fix 1: Strip markdown heading prefix and regenerate missing symbols
            if not year_doc.formatted or not year_doc.formatted.strip():
                updates['formatted'] = format_year_line(year_doc.year).lstrip('# ')
            elif year_doc.formatted.lstrip().startswith('#'):
                updates['formatted'] = year_doc.formatted.lstrip('# ')

            # Fix 2: Finalize past years that are still ongoing
            if year_doc.year < current_year and year_doc.end_time == 0:
                next_year = years_by_num.get(year_doc.year + 1)
                if next_year and next_year.start_time > 0:
                    updates['end_time'] = next_year.start_time
                    updates['duration'] = round((next_year.start_time - year_doc.start_time) / SECONDS_PER_DAY)

            if updates:
                await year_repo.update(guild_id, year_doc.year, **updates)
                logger.info(f'Fixed year {year_doc.year} for guild {guild_id}: {list(updates.keys())}')


# Version 2.2.5
@migration(old='2.2.4', new='2.2.5')
async def migration_add_guild_to_markers():
    """Add guild field to year markers and remove obsolete guild-proxy markers.

    Previously, a dummy marker was stored with channel=guild_id as a timestamp
    reference. All real per-channel markers lacked a guild field, making
    all_for_guild() unable to find them. This migration:
      - Adds guild to every real per-channel marker
      - Deletes the obsolete guild-proxy markers (channel == guild_id)
    """
    from attubot import db
    from attubot.database.repositories import YearMarkerRepository

    logger.info('Running migration to 2.2.5: adding guild field to markers')

    database = db.get_db()
    collection = database[YearMarkerRepository.COLLECTION]

    # Snapshot the collection for rollback
    backup = await _backup_collection(database, YearMarkerRepository.COLLECTION)
    logger.info(f'Snapshotted {len(backup)} marker documents for rollback')

    try:
        # Build reverse map: channel_id -> guild_id from config
        guild_ids = set(config.authorized_guilds)
        channel_to_guild: dict[int, int] = {}
        for guild_id in guild_ids:
            try:
                guild_cfg = config.guild(guild_id)
                for channel_id in guild_cfg.channels.lore_channels:
                    channel_to_guild[channel_id] = guild_id
            except Exception as e:
                logger.error(f'Could not load lore channels for guild {guild_id}: {e}')

        all_docs = await collection.find({}).to_list(length=None)
        updated = deleted = skipped = 0

        for doc in all_docs:
            channel = doc.get('channel')

            if channel in guild_ids:
                # Guild-proxy marker (channel field holds a guild ID) — no longer needed
                await collection.delete_one({'_id': doc['_id']})
                deleted += 1

            elif channel in channel_to_guild:
                guild_id = channel_to_guild[channel]
                await collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'guild': guild_id}},
                )
                updated += 1

            else:
                logger.warn(f'Marker channel={channel} year={doc.get("year")} not found in any guild config, skipping')
                skipped += 1

        logger.info(f'Migration 2.2.5 complete: updated={updated} deleted={deleted} skipped={skipped}')

        # Re-initialize indexes to add the new guild index
        marker_repo = YearMarkerRepository(database)
        await marker_repo.init_indexes()

    except Exception:
        logger.error('Migration 2.2.5 failed — restoring collection from snapshot')
        await _restore_collection(database, YearMarkerRepository.COLLECTION, backup)
        raise


# Version 2.3.0
@migration(old='2.2.5', new='2.3.0')
async def migration_2_3_0():
    """Migration to schema version 2.3.0

    Config file format updated: secrets and connection settings (assets path,
    MongoDB URL/name, web secret key, WebAuthn settings) moved from environment
    variables into the TOML config file under [paths], [database], [auth.web],
    and [auth.webauthn] sections.

    No structural database changes needed — this is a version bump only.
    The version update is handled automatically by the @migration decorator.
    """
    logger.info('Running migration to 2.3.0')


# Version 2.4.0
@migration(old='2.3.0', new='2.4.0')
async def migration_2_4_0():
    """Migration to schema version 2.4.0

    Adds weekly database backup task. Backup settings (path, day, time) are
    configured in the [backup] section of the TOML config file.

    No structural database changes needed — this is a version bump only.
    The version update is handled automatically by the @migration decorator.
    """
    logger.info('Running migration to 2.4.0')
