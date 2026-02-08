"""
AttuBot - Locate Year Markers for Database Storage
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio

from discord import Bot
from discord.utils import snowflake_time
from pydantic import BaseModel

from attubot import config
from attubot.logging import get_logger
from attubot.repositories import YearMarkerRepository

logger = get_logger(__name__)

# Module-level repository instance
_marker_repo: YearMarkerRepository | None = None


def _get_repo() -> YearMarkerRepository:
    """Get or create the marker repository"""
    global _marker_repo  # noqa: PLW0603
    if _marker_repo is None:
        from attubot import db
        _marker_repo = YearMarkerRepository(db.get_db())
    return _marker_repo


# --- Year Marker Model ---

class YearMarker(BaseModel):
    """Year marker runtime model"""
    channel: int
    message: int
    year: int
    exact: bool = False
    wiki_page: bool = False

    async def save(self):
        """Save this marker to MongoDB"""
        await _get_repo().create(
            channel=self.channel,
            message=self.message,
            year=self.year,
            exact=self.exact,
            wiki_page=self.wiki_page,
        )

    async def update(self, **kwargs):
        """Update specific fields and persist to database"""
        # Update instance attributes
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        # Persist to database
        await _get_repo().update(self.channel, self.year, **kwargs)

    async def delete(self):
        """Delete this marker from database"""
        await _get_repo().delete(self.channel, self.year)

    # --- Class Methods for Common Operations ---

    @classmethod
    async def get(cls, channel: int, year: int) -> 'YearMarker | None':
        """Get marker by channel and year"""
        doc = await _get_repo().get(channel, year)
        if doc:
            return cls(
                channel=doc.channel,
                message=doc.message,
                year=doc.year,
                exact=doc.exact,
                wiki_page=doc.wiki_page,
            )
        return None

    @classmethod
    async def total(cls, guild: int | None = None) -> int:
        """Count total markers for a guild"""
        if guild is None:
            guild = config.primary_guild
        return await _get_repo().total(guild)

    @classmethod
    async def timestamp(cls, year: int, guild: int | None = None) -> int:
        """Get timestamp for a year marker (throws exception on invalid year)"""
        if guild is None:
            guild = config.primary_guild

        marker = await _get_repo().get(guild, year)
        if not marker:
            raise Exception(f'No marker found for year {year}')
        return int(snowflake_time(marker.message).timestamp())

    @classmethod
    async def mark(cls, year: int, timestamp: int, channel: int | None = None):
        """Create a new year marker"""
        if channel is None:
            channel = config.primary_guild

        logger.info(f'Marker appended: channel={channel} new={timestamp}')
        await _get_repo().create(channel=channel, year=year, message=timestamp)

    @classmethod
    async def all_for_guild(cls, guild: int) -> list['YearMarker']:
        """Get all markers for a guild"""
        docs = await _get_repo().all_for_guild(guild)
        return [
            cls(
                channel=doc.channel,
                message=doc.message,
                year=doc.year,
                exact=doc.exact,
                wiki_page=doc.wiki_page,
            )
            for doc in docs
        ]

    @classmethod
    async def get_or_create(cls, channel: int, year: int, message: int) -> tuple['YearMarker', bool]:
        """Get existing marker or create new one. Returns (marker, created)"""
        doc, created = await _get_repo().get_or_create(channel, year, message)
        marker = cls(
            channel=doc.channel,
            message=doc.message,
            year=doc.year,
            exact=doc.exact,
            wiki_page=doc.wiki_page,
        )
        return marker, created

    @classmethod
    async def exists(cls, channel: int, year: int) -> bool:
        """Check if a marker exists for the given channel and year"""
        return await _get_repo().exists(channel, year)

# --- Extension Def ---

async def _init_db():
    logger.info('Initializing database')

    # MongoDB initialization is handled by config.on_load()
    # Just set up the repository and indexes
    global _marker_repo  # noqa: PLW0603
    from attubot import db

    _marker_repo = YearMarkerRepository(db.get_db())
    await _marker_repo.init_indexes()

    logger.info(f'Loaded [{await YearMarker.total()}] markers')

    logger.info('Loading config from database')
    await config.on_load()


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_init_db())

