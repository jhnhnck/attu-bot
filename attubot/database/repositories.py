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
    ReloadSignalDocument,
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
