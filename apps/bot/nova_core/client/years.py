# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.years | year model for calendar data storage."""

import structlog
from pydantic import BaseModel

from nova_core.client.calendar import seconds_per_day
from nova_core.client.core import config, db
from nova_core.database.repositories import YearRepository


logger = structlog.stdlib.get_logger(__name__)

# module-level repository instance
_year_repo: YearRepository | None = None


def _get_repo() -> YearRepository:
    """get or create the year repository."""
    global _year_repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _year_repo is None:
        _year_repo = YearRepository(db.get_db())
    return _year_repo


# --- year model ---


class Year(BaseModel):
    """year runtime model - represents a single calendar year for a guild."""

    guild: int
    year: int
    start_time: int
    end_time: int = 0
    duration: int = 0
    notes: str = ''

    async def save(self):
        """save this year to MongoDB."""
        await _get_repo().upsert(
            guild=self.guild,
            year=self.year,
            start_time=self.start_time,
            end_time=self.end_time,
            duration=self.duration,
            notes=self.notes,
        )

    async def update(self, **kwargs):
        """update specific fields and persist to database."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        await _get_repo().update(self.guild, self.year, **kwargs)

    async def delete(self):
        """delete this year from database."""
        await _get_repo().delete(self.guild, self.year)

    def to_span(self):
        """convert to AttuYearSpan for backward compatibility."""
        from nova_core.client.calendar import AttuYearSpan

        return AttuYearSpan(
            start_time=self.start_time,
            end_time=self.end_time,
            duration=self.duration,
        )

    # --- navigation (linking) ---

    async def prev(self) -> 'Year | None':
        """get the previous year, or None if this is year 1."""
        if self.year <= 1:
            return None
        return await Year.get(self.guild, self.year - 1)

    async def next(self) -> 'Year | None':
        """get the next year, or None if not yet stored."""
        return await Year.get(self.guild, self.year + 1)

    # --- class methods ---

    @classmethod
    async def get(cls, guild: int, year: int) -> 'Year | None':
        """get year by guild and year number."""
        doc = await _get_repo().get(guild, year)
        if doc:
            return cls(
                guild=doc.guild,
                year=doc.year,
                start_time=doc.start_time,
                end_time=doc.end_time,
                duration=doc.duration,
                notes=doc.notes,
            )
        return None

    @classmethod
    async def total(cls, guild: int | None = None) -> int:
        """count total stored years for a guild."""
        if guild is None:
            primary = config.get_guild_by_role('primary')
            guild = primary.id if primary is not None else 0
        return await _get_repo().total(guild)

    @classmethod
    async def exists(cls, guild: int, year: int) -> bool:
        """check if a year record exists."""
        return await _get_repo().exists(guild, year)

    @classmethod
    async def all_for_guild(cls, guild: int) -> list['Year']:
        """get all stored years for a guild, sorted by year ascending."""
        docs = await _get_repo().all_for_guild(guild)
        return [
            cls(
                guild=doc.guild,
                year=doc.year,
                start_time=doc.start_time,
                end_time=doc.end_time,
                duration=doc.duration,
                notes=doc.notes,
            )
            for doc in docs
        ]

    @classmethod
    async def get_latest(cls, guild: int) -> 'Year | None':
        """get the most recently stored year for a guild."""
        doc = await _get_repo().get_latest(guild)
        if doc:
            return cls(
                guild=doc.guild,
                year=doc.year,
                start_time=doc.start_time,
                end_time=doc.end_time,
                duration=doc.duration,
                notes=doc.notes,
            )
        return None

    @classmethod
    async def create_from_rollover(cls, guild: int, year: int, start_time: int) -> 'Year':
        """create a new Year record during rollover."""
        new_year = cls(
            guild=guild,
            year=year,
            start_time=start_time,
            end_time=0,
            duration=0,
        )
        await new_year.save()
        return new_year

    @classmethod
    async def finalize(cls, guild: int, year: int, end_time: int) -> 'Year | None':
        """finalize a year by setting its end_time and computing duration."""
        existing = await cls.get(guild, year)
        if existing is None:
            logger.error(f'cannot finalize year {year} for guild {guild}: not found')
            return None

        duration = round((end_time - existing.start_time) / seconds_per_day)
        await existing.update(end_time=end_time, duration=duration)
        return existing
