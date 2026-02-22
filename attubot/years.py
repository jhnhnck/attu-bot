"""
AttuBot - Year Model for Calendar Data Storage
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio

from discord import Bot
from pydantic import BaseModel

from attubot import config
from attubot.calendar import SECONDS_PER_DAY, format_year_line
from attubot.database.repositories import YearRepository
from attubot.logging import get_logger

logger = get_logger(__name__)

# Module-level repository instance
_year_repo: YearRepository | None = None


def _get_repo() -> YearRepository:
    """Get or create the year repository"""
    global _year_repo  # noqa: PLW0603
    if _year_repo is None:
        from attubot import db
        _year_repo = YearRepository(db.get_db())
    return _year_repo


# --- Year Model ---

class Year(BaseModel):
    """Year runtime model - represents a single calendar year for a guild"""
    guild: int
    year: int
    start_time: int
    end_time: int = 0
    duration: int = 0
    formatted: str = ''
    notes: str = ''

    async def save(self):
        """Save this year to MongoDB"""
        await _get_repo().upsert(
            guild=self.guild, year=self.year,
            start_time=self.start_time, end_time=self.end_time,
            duration=self.duration, formatted=self.formatted,
            notes=self.notes,
        )

    async def update(self, **kwargs):
        """Update specific fields and persist to database"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        await _get_repo().update(self.guild, self.year, **kwargs)

    async def delete(self):
        """Delete this year from database"""
        await _get_repo().delete(self.guild, self.year)

    def to_span(self):
        """Convert to AttuYearSpan for backward compatibility"""
        from attubot.calendar import AttuYearSpan
        return AttuYearSpan(
            start_time=self.start_time,
            end_time=self.end_time,
            duration=self.duration,
        )

    # --- Navigation (Linking) ---

    async def prev(self) -> 'Year | None':
        """Get the previous year, or None if this is year 1"""
        if self.year <= 1:
            return None
        return await Year.get(self.guild, self.year - 1)

    async def next(self) -> 'Year | None':
        """Get the next year, or None if not yet stored"""
        return await Year.get(self.guild, self.year + 1)

    # --- Class Methods ---

    @classmethod
    async def get(cls, guild: int, year: int) -> 'Year | None':
        """Get year by guild and year number"""
        doc = await _get_repo().get(guild, year)
        if doc:
            return cls(
                guild=doc.guild, year=doc.year,
                start_time=doc.start_time, end_time=doc.end_time,
                duration=doc.duration, formatted=doc.formatted,
                notes=doc.notes,
            )
        return None

    @classmethod
    async def total(cls, guild: int | None = None) -> int:
        """Count total stored years for a guild"""
        if guild is None:
            guild = config.primary_guild
        return await _get_repo().total(guild)

    @classmethod
    async def exists(cls, guild: int, year: int) -> bool:
        """Check if a year record exists"""
        return await _get_repo().exists(guild, year)

    @classmethod
    async def all_for_guild(cls, guild: int) -> list['Year']:
        """Get all stored years for a guild, sorted by year ascending"""
        docs = await _get_repo().all_for_guild(guild)
        return [
            cls(
                guild=doc.guild, year=doc.year,
                start_time=doc.start_time, end_time=doc.end_time,
                duration=doc.duration, formatted=doc.formatted,
                notes=doc.notes,
            )
            for doc in docs
        ]

    @classmethod
    async def get_latest(cls, guild: int) -> 'Year | None':
        """Get the most recently stored year for a guild"""
        doc = await _get_repo().get_latest(guild)
        if doc:
            return cls(
                guild=doc.guild, year=doc.year,
                start_time=doc.start_time, end_time=doc.end_time,
                duration=doc.duration, formatted=doc.formatted,
                notes=doc.notes,
            )
        return None

    @classmethod
    async def create_from_rollover(cls, guild: int, year: int, start_time: int) -> 'Year':
        """Create a new Year record during rollover with auto-computed formatted line"""
        formatted = format_year_line(year)
        new_year = cls(
            guild=guild, year=year,
            start_time=start_time, end_time=0,
            duration=0, formatted=formatted,
        )
        await new_year.save()
        return new_year

    @classmethod
    async def finalize(cls, guild: int, year: int, end_time: int) -> 'Year | None':
        """Finalize a year by setting its end_time and computing duration"""
        existing = await cls.get(guild, year)
        if existing is None:
            logger.error(f'Cannot finalize year {year} for guild {guild}: not found')
            return None

        duration = round((end_time - existing.start_time) / SECONDS_PER_DAY)
        await existing.update(end_time=end_time, duration=duration)
        return existing


# --- Extension Def ---

async def init_repo():
    """Initialize Year repository and indexes (call after DB is connected)"""
    global _year_repo  # noqa: PLW0603
    from attubot import db

    _year_repo = YearRepository(db.get_db())
    await _year_repo.init_indexes()

    logger.info(f'Loaded [{await Year.total()}] year records')


async def _init_db():
    """Full init: used by bot extension loading"""
    await init_repo()


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_init_db())
