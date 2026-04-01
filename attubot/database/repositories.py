"""
AttuBot - MongoDB Repository Classes
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from typing import TYPE_CHECKING

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from attubot.database.models import (
    ChatCharacterDocument,
    ChatConfigDocument,
    ChatSourceDocument,
    EggDocument,
    EggUserDocument,
    FamilyDocument,
    GuildConfigDocument,
    MessageDocument,
    ReloadSignalDocument,
    StarredMessageDocument,
    SystemConfigDocument,
    ThemeDocument,
    WikiViewDocument,
    YearDocument,
    YearMarkerDocument,
)
from attubot.logging import get_logger


if TYPE_CHECKING:
    from attubot.config import BotTheme, GuildConfig

logger = get_logger(__name__)


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
            saturation=theme.saturation,
            lightness=theme.lightness,
            egg_emojis=theme.egg_emojis,
            progress_emojis=theme.progress_emojis,
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
        # no unique=True: ferretdb uses accessexclusivelock for exclude constraints, locking the table for hours on large collections; deduplication via upsert(filter=message_id)
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

    async def _sync_totals(self, message_id: int) -> StarredMessageDocument | None:
        """recompute and persist total_reactions and weighted_total atomically from stored arrays"""
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            [
                {
                    '$set': {
                        'total_reactions': {
                            '$add': [
                                {'$sum': {'$map': {'input': {'$objectToArray': '$reactions'}, 'in': {'$size': '$$this.v'}}}},
                                {'$sum': {'$map': {'input': {'$objectToArray': '$super_reactions'}, 'in': {'$size': '$$this.v'}}}},
                            ]
                        },
                        'weighted_total': {
                            '$add': [
                                {'$toDouble': {'$sum': {'$map': {'input': {'$objectToArray': '$reactions'}, 'in': {'$size': '$$this.v'}}}}},
                                {'$multiply': [1.5, {'$toDouble': {'$sum': {'$map': {'input': {'$objectToArray': '$super_reactions'}, 'in': {'$size': '$$this.v'}}}}}]},
                            ]
                        },
                    }
                }
            ],
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return StarredMessageDocument(**result)

    async def add_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """add a user to the normal reaction list; skips if they already super-reacted for this emoji.

        returns the updated doc or None if the document was not found.
        """
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        # only update if the user is NOT already in super_reactions for this emoji
        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id, f'super_reactions.{emoji}': {'$ne': user_id}},
            {'$addToSet': {f'reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            # either doc not found or user already has a super reaction - fetch to distinguish
            existing = await self.db[self.COLLECTION].find_one({'message_id': message_id})
            if existing is None:
                return None
            existing.pop('_id', None)
            return StarredMessageDocument(**existing)
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def add_super_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """add a user to the super reaction list; removes them from normal reactions if present.

        returns the updated doc or None if the document was not found.
        """
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {
                '$addToSet': {f'super_reactions.{emoji}': user_id},
                '$pull': {f'reactions.{emoji}': user_id},
            },
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def remove_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """remove a user from the normal reaction list; returns the updated doc or None if not found"""
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$pull': {f'reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def remove_super_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """remove a user from the super reaction list; returns the updated doc or None if not found"""
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$pull': {f'super_reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def clear_emoji_reactions(self, message_id: int, emoji: str) -> StarredMessageDocument | None:
        """clear all normal and super reactions for a specific emoji; returns updated doc or None if not found."""
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$unset': {f'reactions.{emoji}': '', f'super_reactions.{emoji}': ''}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def clear_all_reactions(self, message_id: int) -> StarredMessageDocument | None:
        """clear all reactions (all emojis, normal and super) from a message; returns updated doc or None if not found."""
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$set': {'reactions': {}, 'super_reactions': {}}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def set_starboard_message(self, message_id: int, starboard_message_id: int | None):
        """link or unlink a starboard channel post to this document"""
        result = await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'starboard_message_id': starboard_message_id}},
        )
        if result.matched_count == 0:
            logger.warn(f'starboard: set_starboard_message matched 0 docs for message_id {message_id}')

    async def set_reply_created(self, message_id: int):
        """mark that a reply post has been sent for an uneditable predecessor post"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'reply_created': True}},
        )

    async def delete(self, message_id: int) -> bool:
        """delete a starred message document by message_id; returns True if a document was deleted"""
        result = await self.db[self.COLLECTION].delete_one({'message_id': message_id})
        return result.deleted_count > 0

    async def get_random(self, guild_id: int, min_total: int, max_total: int | None = None) -> StarredMessageDocument | None:
        """return a random document matching the total_reactions range using $sample"""
        match: dict = {'guild_id': guild_id, 'total_reactions': {'$gte': min_total}}
        if max_total is not None:
            match['total_reactions']['$lte'] = max_total
        pipeline = [{'$match': match}, {'$sample': {'size': 1}}]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
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
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def leaderboard_most_starred(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by number of messages that reached the starboard"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'starboard_message_id': {'$ne': None}}},
            {'$group': {'_id': '$author_id', 'starred_messages': {'$sum': 1}}},
            {'$sort': {'starred_messages': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
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
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
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
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        return docs[0]['total'] if docs else 0

    async def all_for_guild(self, guild_id: int) -> list[StarredMessageDocument]:
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = await cursor.to_list(length=None)
        return [StarredMessageDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]

    async def get_all_pending(self, guild_id: int) -> list[StarredMessageDocument]:
        """return starred docs that have not yet been posted to the starboard channel"""
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id, 'starboard_message_id': None})
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
        # no unique=True: ferretdb uses accessexclusivelock for unique constraints; rapid-save coalescing happens via upsert filter match instead.
        # if an older unique index exists under the same auto-generated name, drop it first to avoid IndexKeySpecsConflict (code 86).
        from pymongo.errors import OperationFailure

        try:
            await self.db[self.COLLECTION].create_index(
                [('signal_type', ASCENDING), ('guild_id', ASCENDING)],
            )
        except OperationFailure as e:
            if e.code == 86:
                await self.db[self.COLLECTION].drop_index('signal_type_1_guild_id_1')
                await self.db[self.COLLECTION].create_index(
                    [('signal_type', ASCENDING), ('guild_id', ASCENDING)],
                )
            else:
                raise

    async def send(self, signal_type: str, guild_id: int | None = None):
        """Upsert a reload signal - idempotent for the same (type, guild) pair"""
        doc = ReloadSignalDocument.make(signal_type, guild_id).model_dump()  # type: ignore[arg-type]
        await self.db[self.COLLECTION].update_one(
            {'signal_type': signal_type, 'guild_id': guild_id},
            {'$set': doc},
            upsert=True,
        )

    async def consume_all(self) -> list[ReloadSignalDocument]:
        """Fetch and delete all pending signals one at a time (find_one_and_delete avoids $in on _id which has FerretDB compat issues)"""
        results = []
        while True:
            doc = await self.db[self.COLLECTION].find_one_and_delete({})
            if doc is None:
                break
            doc.pop('_id', None)
            results.append(ReloadSignalDocument(**doc))
        return results


class FamilyRepository:
    """Repository for registered FamilyEcho family trees"""

    COLLECTION = 'families'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        """Create required indexes"""
        await self.db[self.COLLECTION].create_index([('guild_id', ASCENDING), ('name', ASCENDING)], unique=True)

    async def upsert(self, doc: FamilyDocument) -> None:
        """Save or update a family record keyed by (guild_id, name)"""
        await self.db[self.COLLECTION].update_one(
            {'guild_id': doc.guild_id, 'name': doc.name},
            {'$set': doc.model_dump()},
            upsert=True,
        )

    async def get(self, guild_id: int, name: str) -> FamilyDocument | None:
        """Fetch a family by guild and normalized name"""
        doc = await self.db[self.COLLECTION].find_one({'guild_id': guild_id, 'name': name})
        if doc:
            doc.pop('_id', None)
            return FamilyDocument(**doc)
        return None

    async def list_all(self, guild_id: int) -> list[FamilyDocument]:
        """List all registered families for a guild"""
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = await cursor.to_list(length=None)
        return [FamilyDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]


class ChatConfigRepository:
    """Repository for runtime chat/RAG configuration stored in global_config collection"""

    COLLECTION = 'global_config'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def get(self) -> ChatConfigDocument | None:
        """Fetch the chat config document"""
        doc = await self.db[self.COLLECTION].find_one({'config_type': 'chat'})
        if doc:
            doc.pop('_id', None)
            return ChatConfigDocument(**doc)
        return None

    async def save(self, doc: ChatConfigDocument) -> None:
        """Upsert the chat config document"""
        await self.db[self.COLLECTION].update_one(
            {'config_type': 'chat'},
            {'$set': doc.model_dump()},
            upsert=True,
        )


class ChatSourceRepository:
    """Repository for tracking all ingested content (wiki, discord, documents, images)"""

    COLLECTION = 'chat_sources'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self) -> None:
        """Create required indexes"""
        await self.db[self.COLLECTION].create_index('source_id', unique=True)
        await self.db[self.COLLECTION].create_index('source_type')

    async def get(self, source_id: str) -> ChatSourceDocument | None:
        """Fetch a source record by source_id"""
        doc = await self.db[self.COLLECTION].find_one({'source_id': source_id})
        if doc:
            doc.pop('_id', None)
            return ChatSourceDocument(**doc)
        return None

    async def upsert(self, doc: ChatSourceDocument) -> None:
        """Save or update a source record keyed by source_id"""
        await self.db[self.COLLECTION].update_one(
            {'source_id': doc.source_id},
            {'$set': doc.model_dump()},
            upsert=True,
        )

    async def flag_incorrect(self, source_id: str) -> None:
        """Mark a source as incorrect - prevents re-ingestion on next scheduled run"""
        await self.db[self.COLLECTION].update_one(
            {'source_id': source_id},
            {'$set': {'flagged_incorrect': True}},
        )

    async def get_by_type(self, source_type: str) -> list[ChatSourceDocument]:
        """Fetch all source records of a given type"""
        cursor = self.db[self.COLLECTION].find({'source_type': source_type})
        docs = await cursor.to_list(length=None)
        return [ChatSourceDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]


class ChatCharacterRepository:
    """Repository for dynamically discovered character records from the character log channel"""

    COLLECTION = 'chat_characters'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self) -> None:
        """Create required indexes"""
        await self.db[self.COLLECTION].create_index(
            [('user_id', ASCENDING), ('character_name', ASCENDING)],
            unique=True,
        )

    async def get_all(self) -> list[ChatCharacterDocument]:
        """Fetch all known character records"""
        cursor = self.db[self.COLLECTION].find()
        docs = await cursor.to_list(length=None)
        return [ChatCharacterDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]

    async def upsert(self, doc: ChatCharacterDocument) -> None:
        """Insert or update a character record; first_seen_* fields are set only on insert"""
        await self.db[self.COLLECTION].update_one(
            {'user_id': doc.user_id, 'character_name': doc.character_name},
            {
                '$set': {'source_channel_id': doc.source_channel_id, 'notes': doc.notes},
                '$setOnInsert': {
                    'user_id': doc.user_id,
                    'character_name': doc.character_name,
                    'first_seen_timestamp': doc.first_seen_timestamp,
                    'first_seen_message_id': doc.first_seen_message_id,
                },
            },
            upsert=True,
        )


class EggRepository:
    """Repository for egg collection documents"""

    COLLECTION = 'eggs'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self) -> None:
        """Create required indexes"""
        await self.db[self.COLLECTION].create_index('egg_id', unique=True)
        # covers get_oldest_ready() and get_next_unhatched() filter + sort on hatches_at
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('user_id', ASCENDING), ('hatched', ASCENDING), ('hatches_at', ASCENDING)],
        )

    async def insert(self, doc: EggDocument) -> None:
        """Insert a new egg"""
        await self.db[self.COLLECTION].insert_one(doc.model_dump())

    async def get(self, egg_id: str) -> EggDocument | None:
        """Fetch egg by egg_id"""
        doc = await self.db[self.COLLECTION].find_one({'egg_id': egg_id})
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def get_oldest_ready(self, guild_id: int, user_id: int) -> EggDocument | None:
        """Fetch the oldest unhatched egg that is ready to hatch"""
        import time

        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False, 'hatches_at': {'$lte': time.time()}},
            sort=[('hatches_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def get_next_unhatched(self, guild_id: int, user_id: int) -> EggDocument | None:
        """Fetch the next unhatched egg (soonest hatches_at)"""
        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False},
            sort=[('hatches_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def mark_hatched(self, egg_id: str, result: str) -> None:
        """Mark an egg as hatched and set its result"""
        await self.db[self.COLLECTION].update_one(
            {'egg_id': egg_id},
            {'$set': {'hatched': True, 'result': result}},
        )

    async def update_message_id(self, egg_id: str, message_id: int) -> None:
        """Store the thread message id for this egg"""
        await self.db[self.COLLECTION].update_one(
            {'egg_id': egg_id},
            {'$set': {'message_id': message_id}},
        )

    async def count_hatched(self) -> int:
        """Return total count of hatched eggs across all guilds"""
        return await self.db[self.COLLECTION].count_documents({'hatched': True})

    async def get_user_egg_stats(self, guild_id: int, user_id: int) -> 'tuple[int, int, dict[str, int]]':
        """Return (total_collected, total_hatched, unique_results_per_rarity) in one query.

        unique_results_per_rarity maps rarity -> count of distinct creature emojis hatched.
        """
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'user_id': user_id},
            projection={'rarity': 1, 'result': 1, 'hatched': 1, '_id': 0},
        )
        total_collected = 0
        total_hatched = 0
        seen: dict[str, set[str]] = {}
        async for doc in cursor:
            total_collected += 1
            if doc.get('hatched'):
                total_hatched += 1
                rarity = doc['rarity']
                result = doc.get('result') or ''
                if result:
                    seen.setdefault(rarity, set()).add(result)
        return total_collected, total_hatched, {r: len(s) for r, s in seen.items()}

    async def leaderboard_most_hatched(self, guild_id: int, limit: int = 10) -> list[dict]:
        """Return top users by total hatched egg count for a guild"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'hatched': True}},
            {'$group': {'_id': '$user_id', 'total': {'$sum': 1}}},
            {'$sort': {'total': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def leaderboard_most_unique(self, guild_id: int, limit: int = 10) -> list[dict]:
        """Return top users by count of distinct hatched creature types for a guild"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'hatched': True, 'result': {'$ne': None}}},
            {'$group': {'_id': {'user_id': '$user_id', 'result': '$result'}}},
            {'$group': {'_id': '$_id.user_id', 'unique': {'$sum': 1}}},
            {'$sort': {'unique': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def transfer(self, egg_id: str, new_user_id: int, new_message_id: int) -> None:
        """Transfer egg ownership and update its thread message id"""
        await self.db[self.COLLECTION].update_one(
            {'egg_id': egg_id},
            {'$set': {'user_id': new_user_id, 'message_id': new_message_id}},
        )

    async def get_oldest_unhatched_by_rarity(self, guild_id: int, user_id: int, rarity: str) -> 'EggDocument | None':
        """Fetch the oldest unhatched egg of a specific rarity for a user"""
        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False, 'rarity': rarity},
            sort=[('hatches_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def get_oldest_hatched_by_result(self, guild_id: int, user_id: int, result: str) -> 'EggDocument | None':
        """Fetch the oldest hatched egg with a specific result emoji for a user"""
        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': True, 'result': result},
            sort=[('collected_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def list_unhatched(self, guild_id: int, user_id: int) -> 'list[EggDocument]':
        """Return all unhatched eggs for a user, sorted by hatches_at ascending"""
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False},
            sort=[('hatches_at', ASCENDING)],
        )
        docs = []
        async for doc in cursor:
            doc.pop('_id', None)
            docs.append(EggDocument(**doc))
        return docs

    async def list_hatched(self, guild_id: int, user_id: int) -> 'list[EggDocument]':
        """Return all hatched eggs for a user, sorted by collected_at ascending"""
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': True},
            sort=[('collected_at', ASCENDING)],
        )
        docs = []
        async for doc in cursor:
            doc.pop('_id', None)
            docs.append(EggDocument(**doc))
        return docs


class EggUserRepository:
    """Repository for per-user egg state documents"""

    COLLECTION = 'egg_users'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self) -> None:
        """Create required indexes"""
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('user_id', ASCENDING)],
            unique=True,
        )

    async def get(self, guild_id: int, user_id: int) -> EggUserDocument | None:
        """Fetch user egg state"""
        doc = await self.db[self.COLLECTION].find_one({'guild_id': guild_id, 'user_id': user_id})
        if doc:
            doc.pop('_id', None)
            return EggUserDocument(**doc)
        return None

    async def upsert(self, doc: EggUserDocument) -> None:
        """Insert or update user egg state"""
        await self.db[self.COLLECTION].update_one(
            {'guild_id': doc.guild_id, 'user_id': doc.user_id},
            {'$set': doc.model_dump()},
            upsert=True,
        )

    async def update_field(self, guild_id: int, user_id: int, field: str, value) -> None:
        """Update a single field on the user egg state"""
        await self.db[self.COLLECTION].update_one(
            {'guild_id': guild_id, 'user_id': user_id},
            {'$set': {field: value}},
            upsert=True,
        )

    async def list_all(self, guild_id: int) -> list[EggUserDocument]:
        """Return all egg user documents for a guild"""
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = []
        async for doc in cursor:
            doc.pop('_id', None)
            docs.append(EggUserDocument(**doc))
        return docs


class WikiViewRepository:
    """Repository for persistent wiki lookup view state"""

    COLLECTION = 'wiki_views'

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def init_indexes(self) -> None:
        await self.db[self.COLLECTION].create_index('message_id', unique=True)
        await self.db[self.COLLECTION].create_index('expires_at')

    async def upsert(self, doc: WikiViewDocument) -> None:
        """Insert or update view state"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': doc.message_id},
            {'$set': doc.model_dump()},
            upsert=True,
        )

    async def get(self, message_id: int) -> WikiViewDocument | None:
        """Fetch view state by message id"""
        raw = await self.db[self.COLLECTION].find_one({'message_id': message_id})
        if raw:
            raw.pop('_id', None)
            return WikiViewDocument(**raw)
        return None

    async def delete(self, message_id: int) -> None:
        """Delete view state by message id"""
        await self.db[self.COLLECTION].delete_one({'message_id': message_id})

    async def delete_expired(self) -> int:
        """Delete all expired view documents; returns count deleted"""
        import time

        result = await self.db[self.COLLECTION].delete_many({'expires_at': {'$lte': time.time()}})
        return result.deleted_count

    async def all_active(self) -> list[WikiViewDocument]:
        """Return all non-expired view documents"""
        import time

        docs = await self.db[self.COLLECTION].find({'expires_at': {'$gt': time.time()}}).to_list(None)
        return [WikiViewDocument(**{k: v for k, v in d.items() if k != '_id'}) for d in docs]
