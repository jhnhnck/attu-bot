"""
AttuBot - MongoDB Repository Classes
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import TYPE_CHECKING

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from attubot.database.models import (
    GuildConfigDocument,
    MessageDocument,
    ReloadSignalDocument,
    StarredMessageDocument,
    SystemConfigDocument,
    ThemeDocument,
    YearDocument,
    YearMarkerDocument,
)

if TYPE_CHECKING:
    from attubot.config import BotTheme, GuildConfig


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

    async def create(self, guild: int, year: int, start_time: int,
                     end_time: int = 0, duration: int = 0, formatted: str = '', notes: str = ''):
        """Create new year record"""
        doc = YearDocument(
            guild=guild, year=year, start_time=start_time,
            end_time=end_time, duration=duration, formatted=formatted, notes=notes,
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

    async def upsert(self, guild: int, year: int, start_time: int,
                     end_time: int = 0, duration: int = 0, formatted: str = '', notes: str = ''):
        """Insert or update year record (upsert)"""
        doc = YearDocument(
            guild=guild, year=year, start_time=start_time,
            end_time=end_time, duration=duration, formatted=formatted, notes=notes,
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
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('channel_id', ASCENDING), ('message_id', ASCENDING)],
            unique=True,
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
            {'$set': {'content': content, 'edited_at': edited_at}},
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
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'channel_id': channel_id},
        ).sort('message_id', -1).limit(1)
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
        """Return all unique author_ids stored for a guild."""
        return await self.db[self.COLLECTION].distinct('author_id', {'guild_id': guild_id})

    async def update_author_name(self, author_id: int, author_name: str) -> int:
        """Set author_name on every message by this author; returns modified count."""
        result = await self.db[self.COLLECTION].update_many(
            {'author_id': author_id},
            {'$set': {'author_name': author_name}},
        )
        return result.modified_count


class StarboardRepository:
    """Repository for starred message documents"""
    COLLECTION = 'starboard'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        await self.db[self.COLLECTION].create_index('message_id', unique=True)
        await self.db[self.COLLECTION].create_index('guild_id')
        await self.db[self.COLLECTION].create_index('author_id')
        await self.db[self.COLLECTION].create_index('starboard_message_id')
        await self.db[self.COLLECTION].create_index('total_reactions')

    async def get(self, message_id: int) -> StarredMessageDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'message_id': message_id})
        if doc:
            doc.pop('_id', None)
            return StarredMessageDocument(**doc)
        return None

    async def get_by_starboard_message(self, starboard_message_id: int) -> StarredMessageDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'starboard_message_id': starboard_message_id})
        if doc:
            doc.pop('_id', None)
            return StarredMessageDocument(**doc)
        return None

    async def upsert(self, doc: StarredMessageDocument):
        """insert or update a starred message document"""
        data = doc.model_dump()
        await self.db[self.COLLECTION].update_one(
            {'message_id': doc.message_id},
            {'$set': data},
            upsert=True,
        )

    async def add_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """add a user to an emoji's reaction list; returns the updated doc or None if not found"""
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$addToSet': {f'reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        doc = StarredMessageDocument(**result)
        # recompute and persist total_reactions
        total = sum(len(v) for v in doc.reactions.values())
        if total != doc.total_reactions:
            await self.db[self.COLLECTION].update_one(
                {'message_id': message_id},
                {'$set': {'total_reactions': total}},
            )
            doc.total_reactions = total
        return doc

    async def remove_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """remove a user from an emoji's reaction list; returns the updated doc or None if not found"""
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$pull': {f'reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        doc = StarredMessageDocument(**result)
        total = sum(len(v) for v in doc.reactions.values())
        if total != doc.total_reactions:
            await self.db[self.COLLECTION].update_one(
                {'message_id': message_id},
                {'$set': {'total_reactions': total}},
            )
            doc.total_reactions = total
        return doc

    async def set_starboard_message(self, message_id: int, starboard_message_id: int | None):
        """link or unlink a starboard channel post to this document"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'starboard_message_id': starboard_message_id}},
        )

    async def get_random(self, guild_id: int, min_total: int, max_total: int | None = None) -> StarredMessageDocument | None:
        """return a random document matching the total_reactions range using $sample"""
        match: dict = {'guild_id': guild_id, 'total_reactions': {'$gte': min_total}}
        if max_total is not None:
            match['total_reactions']['$lte'] = max_total
        pipeline = [{'$match': match}, {'$sample': {'size': 1}}]
        cursor = self.db[self.COLLECTION].aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        if docs:
            docs[0].pop('_id', None)
            return StarredMessageDocument(**docs[0])
        return None

    async def leaderboard_most_stars(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by total stars received (sum of all reaction list lengths on their messages)"""
        pipeline = [
            {'$match': {'guild_id': guild_id}},
            {'$project': {'author_id': 1, 'reactions_arr': {'$objectToArray': '$reactions'}}},
            {'$unwind': '$reactions_arr'},
            {'$project': {'author_id': 1, 'count': {'$size': '$reactions_arr.v'}}},
            {'$group': {'_id': '$author_id', 'total_stars': {'$sum': '$count'}}},
            {'$sort': {'total_stars': -1}},
            {'$limit': limit},
        ]
        cursor = self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def leaderboard_most_starred(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by number of messages that reached the starboard"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'starboard_message_id': {'$ne': None}}},
            {'$group': {'_id': '$author_id', 'starred_messages': {'$sum': 1}}},
            {'$sort': {'starred_messages': -1}},
            {'$limit': limit},
        ]
        cursor = self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def leaderboard_most_given(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by total stars given across all emojis"""
        pipeline = [
            {'$match': {'guild_id': guild_id}},
            {'$project': {'reactions_arr': {'$objectToArray': '$reactions'}}},
            {'$unwind': '$reactions_arr'},
            {'$unwind': '$reactions_arr.v'},
            {'$group': {'_id': '$reactions_arr.v', 'total_given': {'$sum': 1}}},
            {'$sort': {'total_given': -1}},
            {'$limit': limit},
        ]
        cursor = self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def total_for_guild(self, guild_id: int) -> int:
        """count of all starred message documents for a guild"""
        return await self.db[self.COLLECTION].count_documents({'guild_id': guild_id})

    async def sum_reactions_for_guild(self, guild_id: int) -> int:
        """sum of total_reactions across all documents for a guild"""
        pipeline = [
            {'$match': {'guild_id': guild_id}},
            {'$group': {'_id': None, 'total': {'$sum': '$total_reactions'}}},
        ]
        cursor = self.db[self.COLLECTION].aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        return docs[0]['total'] if docs else 0

    async def all_for_guild(self, guild_id: int) -> list[StarredMessageDocument]:
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = await cursor.to_list(length=None)
        return [StarredMessageDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]


class ReloadSignalRepository:
    """Repository for cross-process config reload signals

    the web process writes signals here; the bot process polls and consumes them.
    documents are upserted by (signal_type, guild_id) so rapid saves coalesce.
    """
    COLLECTION = 'reload_signals'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        await self.db[self.COLLECTION].create_index(
            [('signal_type', ASCENDING), ('guild_id', ASCENDING)],
            unique=True,
        )

    async def send(self, signal_type: str, guild_id: int | None = None):
        """Upsert a reload signal - idempotent for the same (type, guild) pair"""
        doc = ReloadSignalDocument.make(signal_type, guild_id).model_dump()  # type: ignore[arg-type]
        await self.db[self.COLLECTION].update_one(
            {'signal_type': signal_type, 'guild_id': guild_id},
            {'$set': doc},
            upsert=True,
        )

    async def consume_all(self) -> list[ReloadSignalDocument]:
        """Atomically fetch and delete all pending signals"""
        cursor = self.db[self.COLLECTION].find({})
        docs = await cursor.to_list(length=None)
        if not docs:
            return []
        ids = [doc['_id'] for doc in docs]
        await self.db[self.COLLECTION].delete_many({'_id': {'$in': ids}})
        return [ReloadSignalDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]
