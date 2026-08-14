"""
AttuBot - MongoDB Repository Classes
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from typing import TYPE_CHECKING

import structlog
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from .documents import (
    GuildConfigDocument,
    MessageDocument,
    ReloadSignalDocument,
    SystemConfigDocument,
    ThemeDocument,
    YearDocument,
    YearMarkerDocument,
)


if TYPE_CHECKING:
    from nova_core.config import BotTheme, GuildConfig

logger = structlog.stdlib.get_logger(__name__)


class ConfigRepository:
    """Repository for guild and global configuration documents"""

    GUILD_COLLECTION = 'guild_configs'
    GLOBAL_COLLECTION = 'global_config'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        """Create required indexes"""
        await self.db[self.GUILD_COLLECTION].create_index('guild_id', unique=True)
        await self.db[self.GLOBAL_COLLECTION].create_index('config_type', unique=True)

    # Guild config methods
    async def get_guild(self, guild_id: int) -> GuildConfigDocument | None:
        """Fetch guild config by ID"""
        doc = await self.db[self.GUILD_COLLECTION].find_one({'guild_id': guild_id})
        if doc:
            doc.pop('_id', None)
            return GuildConfigDocument(**doc)
        return None

    async def save_guild(self, config: 'GuildConfig'):
        """Save guild config (upsert)"""
        doc = {
            'guild_id': config.id,
            'channels': config.channels.model_dump(),
            'epoch': config.epoch.model_dump(),
            'roles': config.roles.model_dump(),
            'users': config.users.model_dump(),
            'starboard': config.starboard.model_dump(),
            'ccboard': config.ccboard.model_dump(),
        }
        await self.db[self.GUILD_COLLECTION].update_one(
            {'guild_id': config.id},
            {'$set': doc},
            upsert=True,
        )

    async def update_guild_field(self, guild_id: int, field_path: str, value):
        """Update a specific nested field using dot notation"""
        await self.db[self.GUILD_COLLECTION].update_one(
            {'guild_id': guild_id},
            {'$set': {field_path: value}},
        )

    # Global config methods
    async def get_theme(self) -> ThemeDocument | None:
        doc = await self.db[self.GLOBAL_COLLECTION].find_one({'config_type': 'theme'})
        if doc:
            doc.pop('_id', None)
            return ThemeDocument(**doc)
        return None

    async def save_theme(self, theme: 'BotTheme'):
        """Save theme"""
        doc = ThemeDocument(
            rotation=theme.rotation,
            max_rate=theme.max_rate,
            bot_color=theme.bot_color,
            guild_color=theme.guild_color,
            logo_rings=theme.logo_rings,
            logo_planet=theme.logo_planet,
            saturation=theme.saturation,
            lightness=theme.lightness,
            egg_emojis=theme.egg_emojis,
            progress_emojis=theme.progress_emojis,
            ui_emojis=theme.ui_emojis,
        ).model_dump()
        await self.db[self.GLOBAL_COLLECTION].update_one(
            {'config_type': 'theme'},
            {'$set': doc},
            upsert=True,
        )

    async def get_system(self) -> SystemConfigDocument | None:
        doc = await self.db[self.GLOBAL_COLLECTION].find_one({'config_type': 'system'})
        if doc:
            doc.pop('_id', None)
            return SystemConfigDocument(**doc)
        return None

    async def save_system(self, system: SystemConfigDocument):
        """Save system config"""
        await self.db[self.GLOBAL_COLLECTION].update_one(
            {'config_type': 'system'},
            {'$set': system.model_dump()},
            upsert=True,
        )

    async def update_system_field(self, field: str, value):
        await self.db[self.GLOBAL_COLLECTION].update_one(
            {'config_type': 'system'},
            {'$set': {field: value}},
        )


class YearMarkerRepository:
    """Repository for year marker documents"""

    COLLECTION = 'year_markers'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        await self.db[self.COLLECTION].create_index(
            [('channel', ASCENDING), ('year', ASCENDING)],
            unique=True,
        )
        await self.db[self.COLLECTION].create_index('channel')
        await self.db[self.COLLECTION].create_index('guild')

    async def create(self, guild: int, channel: int, message: int, year: int, exact: bool = False, wiki_page: bool = False):
        """Create new marker"""
        doc = YearMarkerDocument(
            guild=guild,
            channel=channel,
            message=message,
            year=year,
            exact=exact,
            wiki_page=wiki_page,
        ).model_dump()
        await self.db[self.COLLECTION].insert_one(doc)

    async def get(self, channel: int, year: int) -> YearMarkerDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'channel': channel, 'year': year})
        if doc:
            doc.pop('_id', None)
            return YearMarkerDocument(**doc)
        return None

    async def get_any_for_guild_year(self, guild: int, year: int) -> YearMarkerDocument | None:
        """Get any marker for a guild+year (used as the canonical timestamp reference)"""
        doc = await self.db[self.COLLECTION].find_one({'guild': guild, 'year': year})
        if doc:
            doc.pop('_id', None)
            return YearMarkerDocument(**doc)
        return None

    async def update(self, channel: int, year: int, **kwargs):
        """Update marker fields"""
        await self.db[self.COLLECTION].update_one(
            {'channel': channel, 'year': year},
            {'$set': kwargs},
        )

    async def upsert(self, guild: int, channel: int, message: int, year: int, exact: bool = False, wiki_page: bool = False):
        """Insert or update marker (upsert)"""
        doc = YearMarkerDocument(
            guild=guild,
            channel=channel,
            message=message,
            year=year,
            exact=exact,
            wiki_page=wiki_page,
        ).model_dump()
        await self.db[self.COLLECTION].update_one(
            {'channel': channel, 'year': year},
            {'$set': doc},
            upsert=True,
        )

    async def delete(self, channel: int, year: int):
        await self.db[self.COLLECTION].delete_one({'channel': channel, 'year': year})

    async def total(self, guild: int) -> int:
        return await self.db[self.COLLECTION].count_documents({'guild': guild})

    async def get_or_create(self, guild: int, channel: int, year: int, message: int):
        """Get existing marker or create new"""
        existing = await self.get(channel, year)
        if existing:
            return existing, False
        await self.create(guild, channel, message, year)
        return await self.get(channel, year), True

    async def exists(self, channel: int, year: int) -> bool:
        count = await self.db[self.COLLECTION].count_documents({'channel': channel, 'year': year})
        return count > 0

    async def all_for_guild(self, guild: int) -> list[YearMarkerDocument]:
        """Get all markers for a guild"""
        cursor = self.db[self.COLLECTION].find({'guild': guild})
        docs = await cursor.to_list(length=None)
        return [YearMarkerDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]


class YearRepository:
    """Repository for year documents"""

    COLLECTION = 'years'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        await self.db[self.COLLECTION].create_index(
            [('guild', ASCENDING), ('year', ASCENDING)],
            unique=True,
        )
        await self.db[self.COLLECTION].create_index('guild')

    async def create(self, guild: int, year: int, start_time: int, end_time: int = 0, duration: int = 0, notes: str = ''):
        """Create new year record"""
        doc = YearDocument(
            guild=guild,
            year=year,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            notes=notes,
        ).model_dump()
        await self.db[self.COLLECTION].insert_one(doc)

    async def get(self, guild: int, year: int) -> YearDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'guild': guild, 'year': year})
        if doc:
            doc.pop('_id', None)
            return YearDocument(**doc)
        return None

    async def update(self, guild: int, year: int, **kwargs):
        """Update year fields"""
        await self.db[self.COLLECTION].update_one(
            {'guild': guild, 'year': year},
            {'$set': kwargs},
        )

    async def upsert(self, guild: int, year: int, start_time: int, end_time: int = 0, duration: int = 0, notes: str = ''):
        """Insert or update year record (upsert)"""
        doc = YearDocument(
            guild=guild,
            year=year,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            notes=notes,
        ).model_dump()
        await self.db[self.COLLECTION].update_one(
            {'guild': guild, 'year': year},
            {'$set': doc},
            upsert=True,
        )

    async def delete(self, guild: int, year: int):
        await self.db[self.COLLECTION].delete_one({'guild': guild, 'year': year})

    async def total(self, guild: int) -> int:
        return await self.db[self.COLLECTION].count_documents({'guild': guild})

    async def get_or_create(self, guild: int, year: int, start_time: int):
        """Get existing year or create new"""
        existing = await self.get(guild, year)
        if existing:
            return existing, False
        await self.create(guild, year, start_time)
        return await self.get(guild, year), True

    async def exists(self, guild: int, year: int) -> bool:
        count = await self.db[self.COLLECTION].count_documents({'guild': guild, 'year': year})
        return count > 0

    async def all_for_guild(self, guild: int) -> list[YearDocument]:
        """Get all years for a guild, sorted by year ascending"""
        cursor = self.db[self.COLLECTION].find({'guild': guild}).sort('year', ASCENDING)
        docs = await cursor.to_list(length=None)
        return [YearDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]

    async def get_latest(self, guild: int) -> YearDocument | None:
        """Get the highest-numbered year for a guild"""
        cursor = self.db[self.COLLECTION].find({'guild': guild}).sort('year', -1).limit(1)
        docs = await cursor.to_list(length=1)
        if docs:
            docs[0].pop('_id', None)
            return YearDocument(**docs[0])
        return None


class MessageRepository:
    """Repository for stored Discord messages"""

    COLLECTION = 'messages'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        # no unique=True: FerretDB uses accessexclusivelock for exclude constraints, locking the table for hours on large collections; deduplication via upsert(filter=message_id)
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('channel_id', ASCENDING), ('message_id', ASCENDING)],
        )
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('channel_id', ASCENDING), ('created_at', ASCENDING)],
        )
        await self.db[self.COLLECTION].create_index('message_id')

    async def upsert(self, doc: MessageDocument):
        """Insert or update a message document"""
        data = doc.model_dump()
        await self.db[self.COLLECTION].update_one(
            {'message_id': doc.message_id},
            {'$set': data},
            upsert=True,
        )

    async def get(self, message_id: int) -> MessageDocument | None:
        """Fetch a message by its ID"""
        doc = await self.db[self.COLLECTION].find_one({'message_id': message_id})
        if doc:
            doc.pop('_id', None)
            return MessageDocument(**doc)
        return None

    async def mark_edited(self, message_id: int, content: str, edited_at: int):
        """Update content and edited timestamp on an existing message"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'content.text': content, 'edited_at': edited_at}},
        )

    async def mark_deleted(self, message_id: int, deleted_at: int):
        """Soft-delete a single message"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'deleted': True, 'deleted_at': deleted_at}},
        )

    async def mark_bulk_deleted(self, message_ids: list[int], deleted_at: int):
        """Soft-delete multiple messages in one operation"""
        await self.db[self.COLLECTION].update_many(
            {'message_id': {'$in': message_ids}},
            {'$set': {'deleted': True, 'deleted_at': deleted_at}},
        )

    async def get_latest_in_channel(self, guild_id: int, channel_id: int) -> int | None:
        """Return the highest message_id stored for a channel (used as backfill cursor)"""
        cursor = (
            self
            .db[self.COLLECTION]
            .find(
                {'guild_id': guild_id, 'channel_id': channel_id},
            )
            .sort('message_id', -1)
            .limit(1)
        )
        docs = await cursor.to_list(length=1)
        if docs:
            return docs[0]['message_id']
        return None

    async def count_for_guild(self, guild_id: int) -> int:
        return await self.db[self.COLLECTION].count_documents({'guild_id': guild_id})

    async def count_for_channel(self, guild_id: int, channel_id: int) -> int:
        return await self.db[self.COLLECTION].count_documents({'guild_id': guild_id, 'channel_id': channel_id})

    async def get_all_message_ids_in_channel(self, guild_id: int, channel_id: int) -> set[int]:
        """Return a set of all stored message_ids for a channel - used for efficient full-scan backfill."""
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'channel_id': channel_id},
            {'_id': 0, 'message_id': 1},
        )
        docs = await cursor.to_list(length=None)
        return {doc['message_id'] for doc in docs}

    async def distinct_author_ids(self, guild_id: int) -> list[int]:
        """Return all unique author ids stored for a guild."""
        return await self.db[self.COLLECTION].distinct('author.id', {'guild_id': guild_id})

    async def update_author_name(self, author_id: int, author_name: str) -> int:
        """Set author.name on every message by this author; returns modified count."""
        result = await self.db[self.COLLECTION].update_many(
            {'author.id': author_id},
            {'$set': {'author.name': author_name}},
        )
        return result.modified_count

    async def find_bot_header(self, guild_id: int, channel_id: int, content_prefix: str, after: int, before: int) -> int | None:
        """Return the message_id of the earliest bot message starting with content_prefix in the time window.

        `after` and `before` are inclusive/exclusive unix timestamps respectively.
        """
        cursor = (
            self
            .db[self.COLLECTION]
            .find({
                'guild_id': guild_id,
                'channel_id': channel_id,
                'author.bot': True,
                'content.text': {'$regex': f'^{re.escape(content_prefix)}'},
                'created_at': {'$gte': after, '$lt': before},
                'deleted': {'$ne': True},
            })
            .sort('created_at', 1)
            .limit(1)
        )
        docs = await cursor.to_list(length=1)
        return docs[0]['message_id'] if docs else None

    async def find_author_message(self, guild_id: int, channel_id: int, author_ids: list[int], after: int, before: int) -> int | None:
        """Return the message_id of the earliest message by any of the given author_ids in the time window."""
        if not author_ids:
            return None
        cursor = (
            self
            .db[self.COLLECTION]
            .find({
                'guild_id': guild_id,
                'channel_id': channel_id,
                'author.id': {'$in': author_ids},
                'created_at': {'$gte': after, '$lt': before},
                'deleted': {'$ne': True},
            })
            .sort('created_at', 1)
            .limit(1)
        )
        docs = await cursor.to_list(length=1)
        return docs[0]['message_id'] if docs else None

    async def find_first_message(self, guild_id: int, channel_id: int, after: int, before: int) -> int | None:
        """Return the message_id of the chronologically first message in the time window."""
        cursor = (
            self
            .db[self.COLLECTION]
            .find({
                'guild_id': guild_id,
                'channel_id': channel_id,
                'created_at': {'$gte': after, '$lt': before},
                'deleted': {'$ne': True},
            })
            .sort('created_at', 1)
            .limit(1)
        )
        docs = await cursor.to_list(length=1)
        return docs[0]['message_id'] if docs else None

    async def get_message_ids_in_window(self, guild_id: int, channel_id: int, after: int, before: int) -> list[int]:
        """Return message ids created within [after, before) that are not already deleted."""
        cursor = self.db[self.COLLECTION].find(
            {
                'guild_id': guild_id,
                'channel_id': channel_id,
                'created_at': {'$gte': after, '$lt': before},
                'deleted': {'$ne': True},
            },
            {'_id': 0, 'message_id': 1},
        )
        docs = await cursor.to_list(length=None)
        return [doc['message_id'] for doc in docs]

    async def get_in_channels_since(self, guild_id: int, channel_ids: list[int], since_timestamp: int) -> list[MessageDocument]:
        """Fetch all non-deleted messages from the given channels since since_timestamp, sorted by created_at asc."""
        if not channel_ids:
            return []
        cursor = (
            self
            .db[self.COLLECTION]
            .find({
                'guild_id': guild_id,
                'channel_id': {'$in': channel_ids},
                'created_at': {'$gte': since_timestamp},
                'deleted': {'$ne': True},
            })
            .sort('created_at', ASCENDING)
        )
        docs = await cursor.to_list(length=None)
        return [MessageDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]


class ReloadSignalRepository:
    """Repository for cross-process config reload signals.

    the web process writes signals; consumers (bot, ingestor) each poll and consume
    only documents addressed to their own `target`. documents are upserted by
    (target, signal_type, guild_id) so rapid saves coalesce per target without one
    consumer stealing another's signal.
    """

    COLLECTION = 'reload_signals'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        # no unique=True: FerretDB uses accessexclusivelock for unique constraints; rapid-save coalescing happens via upsert filter match instead
        # the legacy (signal_type, guild_id) index is dropped by the 2.5.5 migration; recover from a leftover conflict (code 86) just in case
        from pymongo.errors import OperationFailure

        try:
            await self.db[self.COLLECTION].create_index(
                [('target', ASCENDING), ('signal_type', ASCENDING), ('guild_id', ASCENDING)],
            )
        except OperationFailure as e:
            if e.code == 86:
                await self.db[self.COLLECTION].drop_index('target_1_signal_type_1_guild_id_1')
                await self.db[self.COLLECTION].create_index(
                    [('target', ASCENDING), ('signal_type', ASCENDING), ('guild_id', ASCENDING)],
                )
            else:
                raise

    async def send(self, signal_type: str, guild_id: int | None = None, target: str = 'bot'):
        """Upsert a reload signal addressed to a single consumer (target)."""
        doc = ReloadSignalDocument.make(signal_type, guild_id, target).model_dump()  # type: ignore[arg-type]
        await self.db[self.COLLECTION].update_one(
            {'target': target, 'signal_type': signal_type, 'guild_id': guild_id},
            {'$set': doc},
            upsert=True,
        )

    async def consume_all(self, target: str = 'bot') -> list[ReloadSignalDocument]:
        """Fetch and delete all pending signals for the given target (find_one_and_delete avoids $in on _id which has FerretDB compat issues)"""
        results = []
        while True:
            doc = await self.db[self.COLLECTION].find_one_and_delete({'target': target})
            if doc is None:
                break
            doc.pop('_id', None)
            results.append(ReloadSignalDocument(**doc))
        return results
