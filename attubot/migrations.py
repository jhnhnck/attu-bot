"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from collections.abc import Callable

from attubot import config
from attubot.logging import get_logger


logger = get_logger(__name__)

# load-stage migrations run during config.on_load() before bot is connected
load_migration_table: list[Callable] = []
# ready-stage migrations run during config.on_ready() after bot cache is populated
ready_migration_table: list[Callable] = []


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


def migration(old: str, new: str, stage: str = 'load') -> Callable:
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

        if stage == 'ready':
            ready_migration_table.append(wrapper)
        else:
            load_migration_table.append(wrapper)
        return wrapper

    return decorator_migration


# --- Migration Steps ---
# load-stage migrations run before the bot connects; ready-stage run after on_ready().
# migrations must be defined in strict chronological order within each stage.


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
    pass


# Version 2.1.0
@migration(old='2.0.0', new='2.1.0')
async def migration_2_1_0():
    pass


# Version 2.2.0
@migration(old='2.1.0', new='2.2.0')
async def migration_2_2_0():
    pass


# Version 2.2.1
@migration(old='2.2.0', new='2.2.1')
async def migration_backfill_years():
    """Backfill Year documents from existing YearMarker timestamps"""
    from attubot import db
    from attubot.calendar import SECONDS_PER_DAY, get_year_status
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

            await year_repo.upsert(
                guild=guild_id,
                year=yr,
                start_time=start_ts,
                end_time=end_ts,
                duration=duration,
            )
            count += 1

        logger.info(f'Backfilled {count} year records for guild {guild_id}')


# Version 2.2.3 - no-op; version bump only
@migration(old='2.2.1', new='2.2.3')
async def migration_2_2_3():
    pass


# Version 2.2.4
@migration(old='2.2.3', new='2.2.4')
async def migration_fix_year_data():
    """Fix year data: strip markdown headings, regenerate missing symbols, finalize past years"""
    from attubot import db
    from attubot.calendar import SECONDS_PER_DAY, get_year_status
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

            # finalize past years that are still marked as ongoing
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
                # guild-proxy marker (channel field holds a guild ID) — no longer needed
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

        # re-initialize indexes to add the new guild index
        marker_repo = YearMarkerRepository(database)
        await marker_repo.init_indexes()

    except Exception:
        logger.error('Migration 2.2.5 failed — restoring collection from snapshot')
        await _restore_collection(database, YearMarkerRepository.COLLECTION, backup)
        raise


# Version 2.3.0
@migration(old='2.2.5', new='2.3.0')
async def migration_2_3_0():
    """Config file format updated: secrets and connection settings moved from env vars into TOML."""
    logger.info('Running migration to 2.3.0')


# Version 2.4.0
@migration(old='2.3.0', new='2.4.0')
async def migration_2_4_0():
    """Adds weekly database backup task."""
    logger.info('Running migration to 2.4.0')


# Version 2.4.1 - no-op; version already written to DB before thread fix was ready
@migration(old='2.4.0', new='2.4.1')
async def migration_2_4_1():
    pass


# Version 2.4.2 - no-op; thread backfill attempted here but bot cache not yet ready
@migration(old='2.4.1', new='2.4.2')
async def migration_2_4_2():
    pass


# Version 2.4.3 (ready)
@migration(old='2.4.2', new='2.4.3', stage='ready')
async def migration_fix_thread_parent_ids():
    """Backfill parent_channel_id on stored messages that were sent in threads.

    Previous attempts (2.4.1 and 2.4.2) ran during on_load() before the bot's
    channel cache was populated, so all thread channels were skipped. This migration
    runs during on_ready() when active threads are fully cached.

    Superseded by 2.4.4 which also covers archived threads via the API.
    """
    import discord as _discord

    from attubot import bot, db
    from attubot.database.repositories import MessageRepository

    logger.info('Running migration to 2.4.3: backfilling parent_channel_id on thread messages')

    database = db.get_db()
    collection = database[MessageRepository.COLLECTION]

    # find all distinct channel_ids where parent_channel_id is not yet set
    pipeline = [
        {'$match': {'parent_channel_id': None}},
        {'$group': {'_id': '$channel_id'}},
    ]
    cursor = await collection.aggregate(pipeline)
    rows = await cursor.to_list(length=None)
    channel_ids = [row['_id'] for row in rows]
    logger.info(f'Checking {len(channel_ids)} distinct channel ids for thread membership')

    fixed = 0
    skipped = 0
    for channel_id in channel_ids:
        ch = bot.get_channel(channel_id)
        if not isinstance(ch, _discord.Thread):
            skipped += 1
            continue
        result = await collection.update_many(
            {'channel_id': channel_id, 'parent_channel_id': None},
            {'$set': {'parent_channel_id': ch.parent_id}},
        )
        fixed += result.modified_count
        logger.debug(f'Set parent_channel_id={ch.parent_id} on {result.modified_count} messages in thread {channel_id}')

    logger.info(f'Migration 2.4.3 complete: updated={fixed} skipped={skipped}')


# Version 2.4.4 (ready)
@migration(old='2.4.3', new='2.4.4', stage='ready')
async def migration_fix_thread_parent_ids_archived():
    """Backfill parent_channel_id for messages in archived threads.

    Migration 2.4.3 only covered threads still in the bot's active cache.
    Archived threads are evicted from the cache and were skipped, leaving their
    messages with parent_channel_id=None. This migration fetches all threads
    (active + archived public + archived private) for every text channel in each
    authorized guild via the Discord API, builds a complete thread->parent map,
    and applies it to any remaining unfixed messages.
    """
    import asyncio

    import discord as _discord

    from attubot import bot, db
    from attubot.database.repositories import MessageRepository

    logger.info('Running migration to 2.4.4: backfilling parent_channel_id for archived threads')

    database = db.get_db()
    collection = database[MessageRepository.COLLECTION]

    # collect the channel_ids still missing a parent
    pipeline = [
        {'$match': {'parent_channel_id': None}},
        {'$group': {'_id': '$channel_id'}},
    ]
    cursor = await collection.aggregate(pipeline)
    rows = await cursor.to_list(length=None)
    unfixed_ids: set[int] = {row['_id'] for row in rows}

    if not unfixed_ids:
        logger.info('Migration 2.4.4: nothing to fix')
        return

    logger.info(f'Found {len(unfixed_ids)} channel ids still missing parent_channel_id')

    # build thread_id -> parent_id map by querying the Discord API for every guild
    thread_to_parent: dict[int, int] = {}

    for guild_id in config.authorized_guilds:
        discord_guild = bot.get_guild(guild_id)
        if discord_guild is None:
            logger.warn(f'Guild {guild_id} not in bot cache, skipping')
            continue

        # active threads - always available from cache after on_ready
        for thread in discord_guild.threads:
            if thread.parent_id is not None:
                thread_to_parent[thread.id] = thread.parent_id

        # archived threads require an API call per parent channel
        text_channels = [ch for ch in discord_guild.channels if isinstance(ch, (_discord.TextChannel, _discord.ForumChannel))]
        for parent_ch in text_channels:
            # public archived threads
            try:
                async for thread in parent_ch.archived_threads(limit=None):
                    thread_to_parent[thread.id] = parent_ch.id
            except (_discord.Forbidden, _discord.HTTPException) as e:
                logger.warn(f'Could not fetch public archived threads for channel {parent_ch.id}: {e}')

            # private archived threads (requires MANAGE_THREADS)
            try:
                async for thread in parent_ch.archived_threads(limit=None, private=True):
                    thread_to_parent[thread.id] = parent_ch.id
            except (_discord.Forbidden, _discord.HTTPException) as e:
                logger.debug(f'Could not fetch private archived threads for channel {parent_ch.id}: {e}')

            # small delay to avoid hitting rate limits across many channels
            await asyncio.sleep(0.5)

    logger.info(f'Discovered {len(thread_to_parent)} total threads across all guilds')

    fixed = 0
    still_missing = 0
    for channel_id in unfixed_ids:
        parent_id = thread_to_parent.get(channel_id)
        if parent_id is None:
            # not a thread, or a thread we genuinely cannot resolve
            still_missing += 1
            continue
        result = await collection.update_many(
            {'channel_id': channel_id, 'parent_channel_id': None},
            {'$set': {'parent_channel_id': parent_id}},
        )
        fixed += result.modified_count
        logger.debug(f'Set parent_channel_id={parent_id} on {result.modified_count} messages in thread {channel_id}')

    logger.info(f'Migration 2.4.4 complete: updated={fixed} unresolvable={still_missing}')


# Version 2.5.0 (ready)
@migration(old='2.4.4', new='2.5.0', stage='ready')
async def migration_drop_formatted():
    """Remove the `formatted` field from all Year documents.

    `formatted` was the pre-computed year header string (e.g. '<<< Year 5 PC <<<').
    It is now generated on demand via `format_year_line(year)` wherever needed, so
    storing it is redundant and makes the schema harder to maintain.
    """
    from attubot import db

    logger.info('Running migration to 2.5.0: removing formatted field from year documents')

    database = db.get_db()
    result = await database['years'].update_many(
        {'formatted': {'$exists': True}},
        {'$unset': {'formatted': ''}},
    )
    logger.info(f'Migration 2.5.0: unset formatted on {result.modified_count} year documents')


# Version 2.5.1 (ready)
@migration(old='2.5.0', new='2.5.1', stage='ready')
async def migration_purge_markers():
    """Remove all existing year marker overrides.

    The new marker resolver derives markers dynamically from stored messages,
    so persisted overrides are no longer needed as a baseline. Any overrides
    that still need to exist can be re-created via /marker save or the web UI.
    """
    from attubot import db
    from attubot.database.repositories import YearMarkerRepository

    logger.info('Running migration to 2.5.1: purging all year marker overrides')

    database = db.get_db()
    result = await database[YearMarkerRepository.COLLECTION].delete_many({})
    logger.info(f'Migration 2.5.1: deleted {result.deleted_count} year marker documents')
