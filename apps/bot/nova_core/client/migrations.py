# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.migrations | configuration migrations."""

from collections.abc import Awaitable, Callable

import structlog

from nova_core.client.core import config


logger = structlog.stdlib.get_logger(__name__)

# decorated migrations always take the current db version string; the original
# `async def step():` body is invoked by the wrapper after the version match.
MigrationFunc = Callable[[str], Awaitable[None]]

# load-stage migrations run during config.on_load() before bot is connected
load_migration_table: list[MigrationFunc] = []
# ready-stage migrations run during config.on_ready() after bot cache is populated
ready_migration_table: list[MigrationFunc] = []


class MigrationError(Exception):
    """raised when a migration fails; signals the bot should not continue initializing."""


# --- runner ---


async def run_pending_migrations(*, stage: str = 'load') -> None:
    """run all pending migrations for the given stage, re-reading the db version after each step."""
    table = ready_migration_table if stage == 'ready' else load_migration_table
    system_config = await config.config_repo.get_system()

    try:
        for fn in table:
            await fn(system_config.version)
            system_config = await config.config_repo.get_system()
    except MigrationError as e:
        logger.critical(f'{stage}-stage migration failed; refusing to continue: {e}')
        raise

    system_config = await config.config_repo.get_system()
    logger.info(f'{stage}-stage migrations complete: now at version {system_config.version}')


# --- backup / restore helpers ---


async def _backup_collection(db, name: str) -> list[dict]:
    """snapshot all documents in a collection for rollback purposes."""
    docs = await db[name].find({}).to_list(length=None)
    return [dict(doc) for doc in docs]


async def _restore_collection(db, name: str, backup: list[dict]):
    """restore a collection from a snapshot, replacing all current contents."""
    await db[name].delete_many({})
    if backup:
        clean = [{k: v for k, v in doc.items() if k != '_id'} for doc in backup]
        await db[name].insert_many(clean)


# --- decorator ---


def migration(old: str, new: str, stage: str = 'load') -> Callable[[Callable[[], Awaitable[None]]], MigrationFunc]:
    def decorator_migration(func: Callable[[], Awaitable[None]]) -> MigrationFunc:
        async def wrapper(version: str) -> None:
            # bail out if we're past this patch
            if version != old:
                logger.debug(f'patch for {new} already applied')
                return

            # call migrator - do NOT bump version if it fails
            try:
                await func()
            except Exception as e:
                logger.error(f'migration to {new} failed: {e}')
                raise MigrationError(f'Migration to {new} failed') from e

            # bump version in MongoDB
            logger.info(f'applied patch for {new}')
            from nova_core.client.core import db

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


# --- migration steps ---
# load-stage migrations run before the bot connects; ready-stage run after on_ready().
# migrations must be defined in strict chronological order within each stage.


# bootstrap: fresh database with no prior version
@migration(old='0.0.0', new='1.8.0-pre9')
async def migration_bootstrap():
    """bootstrap migration for fresh databases."""
    pass


# version 1.8.0
@migration(old='1.8.0-pre9', new='1.8.0')
async def migration_full_release():
    pass


# version 2.0.0
@migration(old='1.8.0', new='2.0.0')
async def migration_2_0_0():
    pass


# version 2.1.0
@migration(old='2.0.0', new='2.1.0')
async def migration_2_1_0():
    pass


# version 2.2.0
@migration(old='2.1.0', new='2.2.0')
async def migration_2_2_0():
    pass


# version 2.2.1
@migration(old='2.2.0', new='2.2.1')
async def migration_backfill_years():
    """backfill Year documents from existing YearMarker timestamps."""
    from nova_core.client.calendar import get_year_status, seconds_per_day
    from nova_core.client.core import db
    from nova_core.client.markers import YearMarker
    from nova_core.database.repositories import YearRepository

    logger.info('running migration to 2.2.1: backfilling year records')

    database = db.get_db()
    year_repo = YearRepository(database)
    await year_repo.init_indexes()

    for guild_id in config.authorized_guilds:
        try:
            _, current_year = get_year_status(guild_id)
        except Exception as e:
            logger.error(f'skipping guild {guild_id} during year backfill: {e}')
            continue

        count = 0
        for yr in range(1, current_year + 1):
            start_ts = await YearMarker.timestamp(yr, guild_id)
            if start_ts is None:
                logger.warning(f'no marker for year {yr} in guild {guild_id}, skipping')
                continue

            end_ts = await YearMarker.timestamp(yr + 1, guild_id) or 0 if yr < current_year else 0
            duration = round((end_ts - start_ts) / seconds_per_day) if end_ts > 0 else 0

            await year_repo.upsert(
                guild=guild_id,
                year=yr,
                start_time=start_ts,
                end_time=end_ts,
                duration=duration,
            )
            count += 1

        logger.info(f'backfilled {count} year records for guild {guild_id}')


# version 2.2.3 - no-op; version bump only
@migration(old='2.2.1', new='2.2.3')
async def migration_2_2_3():
    pass


# version 2.2.4
@migration(old='2.2.3', new='2.2.4')
async def migration_fix_year_data():
    """fix year data: strip markdown headings, regenerate missing symbols, finalize past years."""
    from nova_core.client.calendar import get_year_status, seconds_per_day
    from nova_core.client.core import db
    from nova_core.database.repositories import YearRepository

    logger.info('running migration to 2.2.4: fixing year data')

    database = db.get_db()
    year_repo = YearRepository(database)

    for guild_id in config.authorized_guilds:
        try:
            _, current_year = get_year_status(guild_id)
        except Exception as e:
            logger.error(f'skipping guild {guild_id} during year fix: {e}')
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
                    updates['duration'] = round((next_year.start_time - year_doc.start_time) / seconds_per_day)

            if updates:
                await year_repo.update(guild_id, year_doc.year, **updates)
                logger.info(f'fixed year {year_doc.year} for guild {guild_id}: {list(updates.keys())}')


# version 2.2.5
@migration(old='2.2.4', new='2.2.5')
async def migration_add_guild_to_markers():
    """add guild field to year markers and remove obsolete guild-proxy markers.

    previously, a dummy marker was stored with channel=guild_id as a timestamp
    reference. all real per-channel markers lacked a guild field, making
    all_for_guild() unable to find them. this migration:
      - adds guild to every real per-channel marker
      - deletes the obsolete guild-proxy markers (channel == guild_id)
    """
    from nova_core.client.core import db
    from nova_core.database.repositories import YearMarkerRepository

    logger.info('running migration to 2.2.5: adding guild field to markers')

    database = db.get_db()
    collection = database[YearMarkerRepository.COLLECTION]

    # snapshot the collection for rollback
    backup = await _backup_collection(database, YearMarkerRepository.COLLECTION)
    logger.info(f'snapshotted [{len(backup)}] marker documents for rollback')

    try:
        # build reverse map: channel_id -> guild_id from config
        guild_ids = set(config.authorized_guilds)
        channel_to_guild: dict[int, int] = {}
        for guild_id in guild_ids:
            try:
                guild_cfg = config.guild(guild_id)
                for channel_id in guild_cfg.channels.lore_channels:
                    channel_to_guild[channel_id] = guild_id
            except Exception as e:
                logger.error(f'could not load lore channels for guild {guild_id}: {e}')

        all_docs = await collection.find({}).to_list(length=None)
        updated = deleted = skipped = 0

        for doc in all_docs:
            channel = doc.get('channel')

            if channel in guild_ids:
                # guild-proxy marker (channel field holds a guild ID) - no longer needed
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
                logger.warning(f'marker channel={channel} year={doc.get("year")} not found in any guild config, skipping')
                skipped += 1

        logger.info(f'migration 2.2.5 complete: updated={updated} deleted={deleted} skipped={skipped}')

        # re-initialize indexes to add the new guild index
        marker_repo = YearMarkerRepository(database)
        await marker_repo.init_indexes()

    except Exception:
        logger.error('migration 2.2.5 failed; restoring collection from snapshot')
        await _restore_collection(database, YearMarkerRepository.COLLECTION, backup)
        raise


# version 2.3.0
@migration(old='2.2.5', new='2.3.0')
async def migration_2_3_0():
    """config file format updated: secrets and connection settings moved from env vars into TOML."""
    logger.info('running migration to 2.3.0')


# version 2.4.0
@migration(old='2.3.0', new='2.4.0')
async def migration_2_4_0():
    """adds weekly database backup task."""
    logger.info('running migration to 2.4.0')


# version 2.4.1 - no-op; version already written to DB before thread fix was ready
@migration(old='2.4.0', new='2.4.1')
async def migration_2_4_1():
    pass


# version 2.4.2 - no-op; thread backfill attempted here but bot cache not yet ready
@migration(old='2.4.1', new='2.4.2')
async def migration_2_4_2():
    pass


# version 2.4.3 (ready)
@migration(old='2.4.2', new='2.4.3', stage='ready')
async def migration_fix_thread_parent_ids():
    """backfill parent_channel_id on stored messages that were sent in threads.

    previous attempts (2.4.1 and 2.4.2) ran during on_load() before the bot's
    channel cache was populated, so all thread channels were skipped. this migration
    runs during on_ready() when active threads are fully cached.

    superseded by 2.4.4 which also covers archived threads via the API.
    """
    import discord as _discord

    from nova_core.client.core import bot, db
    from nova_core.database.repositories import MessageRepository

    logger.info('running migration to 2.4.3: backfilling parent_channel_id on thread messages')

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
    logger.info(f'checking [{len(channel_ids)}] distinct channel ids for thread membership')

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
        logger.debug(f'set parent_channel_id={ch.parent_id} on {result.modified_count} messages in thread {channel_id}')

    logger.info(f'migration 2.4.3 complete: updated={fixed} skipped={skipped}')


# version 2.4.4 (ready)
@migration(old='2.4.3', new='2.4.4', stage='ready')
async def migration_fix_thread_parent_ids_archived():
    """backfill parent_channel_id for messages in archived threads.

    migration 2.4.3 only covered threads still in the bot's active cache.
    archived threads are evicted from the cache and were skipped, leaving their
    messages with parent_channel_id=None. this migration fetches all threads
    (active + archived public + archived private) for every text channel in each
    authorized guild via the Discord API, builds a complete thread->parent map,
    and applies it to any remaining unfixed messages.
    """
    import asyncio

    import discord as _discord

    from nova_core.client.core import bot, db
    from nova_core.database.repositories import MessageRepository

    logger.info('running migration to 2.4.4: backfilling parent_channel_id for archived threads')

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
        logger.info('migration 2.4.4: nothing to fix')
        return

    logger.info(f'found [{len(unfixed_ids)}] channel ids still missing parent_channel_id')

    # build thread_id -> parent_id map by querying the Discord API for every guild
    thread_to_parent: dict[int, int] = {}

    for guild_id in config.authorized_guilds:
        discord_guild = bot.get_guild(guild_id)
        if discord_guild is None:
            logger.warning(f'guild {guild_id} not in bot cache, skipping')
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
                logger.warning(f'could not fetch public archived threads for channel {parent_ch.id}: {e}')

            # private archived threads (requires MANAGE_THREADS)
            try:
                async for thread in parent_ch.archived_threads(limit=None, private=True):
                    thread_to_parent[thread.id] = parent_ch.id
            except (_discord.Forbidden, _discord.HTTPException) as e:
                logger.debug(f'could not fetch private archived threads for channel {parent_ch.id}: {e}')

            # small delay to avoid hitting rate limits across many channels
            await asyncio.sleep(0.5)

    logger.info(f'discovered [{len(thread_to_parent)}] total threads across all guilds')

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
        logger.debug(f'set parent_channel_id={parent_id} on {result.modified_count} messages in thread {channel_id}')

    logger.info(f'migration 2.4.4 complete: updated={fixed} unresolvable={still_missing}')


# version 2.5.0 (ready)
@migration(old='2.4.4', new='2.5.0', stage='ready')
async def migration_drop_formatted():
    """remove the `formatted` field from all Year documents.

    `formatted` was the pre-computed year header string (e.g. '<<< Year 5 PC <<<').
    it is now generated on demand via `format_year_line(year)` wherever needed, so
    storing it is redundant and makes the schema harder to maintain.
    """
    from nova_core.client.core import db

    logger.info('running migration to 2.5.0: removing formatted field from year documents')

    database = db.get_db()
    result = await database['years'].update_many(
        {'formatted': {'$exists': True}},
        {'$unset': {'formatted': ''}},
    )
    logger.info(f'migration 2.5.0: unset formatted on {result.modified_count} year documents')


# version 2.5.1 (ready)
@migration(old='2.5.0', new='2.5.1', stage='ready')
async def migration_purge_markers():
    """remove all existing year marker overrides.

    the new marker resolver derives markers dynamically from stored messages,
    so persisted overrides are no longer needed as a baseline. any overrides
    that still need to exist can be re-created via /marker save or the web UI.
    """
    from nova_core.client.core import db
    from nova_core.database.repositories import YearMarkerRepository

    logger.info('running migration to 2.5.1: purging all year marker overrides')

    database = db.get_db()
    result = await database[YearMarkerRepository.COLLECTION].delete_many({})
    logger.info(f'migration 2.5.1: deleted {result.deleted_count} year marker documents')


# version 2.5.2
@migration(old='2.5.1', new='2.5.2')
async def migration_restructure_messages():
    """reshape MessageDocument flat fields into sub-documents.

    groups the previously flat author, content, and cross-reference fields
    into nested sub-documents for a more organized and extensible schema:
      - author_id, author_name, author_bot  ->  author: {id, name, bot}
      - content (str), attachments, embeds, sticker_ids  ->  content: {text, attachments, embeds, sticker_ids}
      - reference_id, starboard_reference_id  ->  refs: {reply_to, starboard_post}
    """
    from nova_core.client.core import db
    from nova_core.database.repositories import MessageRepository

    logger.info('running migration to 2.5.2: restructuring MessageDocument into sub-documents')

    database = db.get_db()
    collection = database[MessageRepository.COLLECTION]

    backup = await _backup_collection(database, MessageRepository.COLLECTION)
    logger.info(f'snapshotted [{len(backup)}] message documents for rollback')

    try:
        result = await collection.update_many(
            {},
            [
                {
                    '$set': {
                        'author': {
                            'id': '$author_id',
                            'name': '$author_name',
                            'bot': {'$ifNull': ['$author_bot', False]},
                        },
                        'content': {
                            'text': {'$ifNull': ['$content', '']},
                            'attachments': {'$ifNull': ['$attachments', []]},
                            'embeds': {'$ifNull': ['$embeds', []]},
                            'sticker_ids': {'$ifNull': ['$sticker_ids', []]},
                        },
                        'refs': {
                            'reply_to': '$reference_id',
                            'starboard_post': '$starboard_reference_id',
                        },
                    }
                },
                {
                    '$unset': [
                        'author_id',
                        'author_name',
                        'author_bot',
                        'attachments',
                        'embeds',
                        'sticker_ids',
                        'reference_id',
                        'starboard_reference_id',
                        # 'content' is overwritten above with the sub-document, not unset separately
                    ]
                },
            ],
        )
        logger.info(f'migration 2.5.2: restructured {result.modified_count} message documents')

    except Exception:
        logger.error('migration 2.5.2 failed; restoring messages collection from snapshot')
        await _restore_collection(database, MessageRepository.COLLECTION, backup)
        raise


# version 2.5.3
@migration(old='2.5.2', new='2.5.3')
async def migration_2_5_3():
    """guild config: primary/secondary keys replace authorized list in attu-bot.toml."""
    logger.info('running migration to 2.5.3')


# version 2.5.4
@migration(old='2.5.3', new='2.5.4')
async def migration_seed_ui_emojis():
    """seed ui_emojis on ThemeDocument with the previously hardcoded emoji IDs."""
    from nova_core.client.core import db

    logger.info('running migration to 2.5.4: seeding ui_emojis')

    database = db.get_db()
    backup = await _backup_collection(database, 'global_config')

    try:
        result = await database.global_config.update_one(
            {'config_type': 'theme', '$or': [{'ui_emojis': {'$exists': False}}, {'ui_emojis': {}}]},
            {
                '$set': {
                    'ui_emojis': {
                        'rockball': 1308981475114225694,
                        'rockball_player': 1308977543034048552,
                        'crackerpeaty': 1214140141245825024,
                        'tieteran_wave': 1308636215930654801,
                    }
                }
            },
        )
        logger.info(f'migration 2.5.4: {"seeded" if result.modified_count else "already populated, skipped"} ui_emojis')

    except Exception:
        logger.error('migration 2.5.4 failed; restoring global_config from snapshot')
        await _restore_collection(database, 'global_config', backup)
        raise


# version 2.5.5
@migration(old='2.5.4', new='2.5.5')
async def migration_target_signals():
    """add target field to reload signals; drop legacy index and purge untargeted docs.

    the (signal_type, guild_id) index is replaced by (target, signal_type, guild_id) so
    bot and ingestor consumers can each drain only their own queue. legacy untargeted
    signals are purged here; init_indexes() builds the new index on the next startup.
    """
    import contextlib

    from pymongo.errors import OperationFailure

    from nova_core.client.core import db
    logger.info('running migration to 2.5.5: targeting reload signals')

    database = db.get_db()
    collection = database['reload_signals']

    with contextlib.suppress(OperationFailure):
        await collection.drop_index('signal_type_1_guild_id_1')

    result = await collection.delete_many({'target': {'$exists': False}})
    logger.info(f'migration 2.5.5: removed {result.deleted_count} legacy untargeted reload signals')
