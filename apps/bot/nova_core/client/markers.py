# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.markers | year marker resolution and override storage."""

import re
import time
from dataclasses import dataclass

import structlog
from discord.utils import snowflake_time
from pydantic import BaseModel

from nova_core.client.core import config, db
from nova_core.database.repositories import MessageRepository, YearMarkerRepository


logger = structlog.stdlib.get_logger(__name__)

# Module-level repository instances
_marker_repo: YearMarkerRepository | None = None
_message_repo: MessageRepository | None = None


def _get_repo() -> YearMarkerRepository:
    """Get or create the marker override repository"""
    global _marker_repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _marker_repo is None:
        _marker_repo = YearMarkerRepository(db.get_db())
    return _marker_repo


def _get_message_repo() -> MessageRepository:
    """Get or create the message repository for resolver queries"""
    global _message_repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _message_repo is None:
        _message_repo = MessageRepository(db.get_db())
    return _message_repo


# --- Marker Detection ---


def has_year_marker(year: int, content: str) -> bool:
    """Return True if message content looks like a year header for the given year.

    matches the bot's format_year_line output OR a human-authored year header
    of the form: (repeated char) (Year? <N> PC?) (repeated char)
    """
    first_line = content.lower().partition('\n')[0]
    # year number present (allow adjacent year-1 for single-digit years)
    if re.search(rf'\b{year}\b', first_line) or (year < 10 and re.search(rf'\b{year - 1}\b', first_line)):
        return 'pc' in first_line or 'year' in first_line
    return False


# --- Resolved Marker ---


@dataclass
class ResolvedMarker:
    """Result of resolving the marker for a (guild, channel, year) triple."""

    guild: int
    channel: int
    year: int
    message: int  # message snowflake; 0 if not found
    exact: bool  # true if bot header, author header, or admin override
    source: str  # 'override' | 'bot' | 'author' | 'first' | 'primary' | 'none'

    @property
    def found(self) -> bool:
        return self.message != 0


async def resolve_marker(guild: int, channel: int, year: int) -> ResolvedMarker:
    """Resolve the canonical marker message for a (guild, channel, year) triple.

    Resolution order:
    1. admin override in year_markers collection
    2. bot rollover header in messages (format_year_line match)
    3. authorized marker-author header message
    4. first chronological message in the year window
    5. primary lore channel's marker (cross-channel fallback)

    returns ResolvedMarker with source='none' and message=0 if nothing found.
    """
    from nova_core.client.calendar import format_year_line

    # 1 - admin override
    override = await _get_repo().get(channel, year)
    if override:
        return ResolvedMarker(guild=guild, channel=channel, year=year, message=override.message, exact=True, source='override')

    # get year window for message queries
    after, before = await _get_year_window(guild, year)
    if after == 0:
        # no timing info at all - try primary fallback immediately
        return await _primary_fallback(guild, channel, year)

    # build content prefix for bot header detection (strips markdown heading markers)
    year_header = format_year_line(year)
    # extract the non-heading portion; re.escape is applied inside find_bot_header
    content_prefix = year_header.lstrip('# ')

    # 2 - bot rollover header
    bot_msg = await _get_message_repo().find_bot_header(guild, channel, content_prefix, after, before)
    if bot_msg:
        return ResolvedMarker(guild=guild, channel=channel, year=year, message=bot_msg, exact=True, source='bot')

    # 3 - authorized marker-author header
    try:
        marker_author_ids = list(config.guild(guild).users.markers)
    except Exception:
        marker_author_ids = []

    if marker_author_ids:
        author_msg = await _get_message_repo().find_author_message(guild, channel, marker_author_ids, after, before)
        if author_msg:
            # verify content looks like a year header before accepting
            msg_doc = await _get_message_repo().get(author_msg)
            if msg_doc and has_year_marker(year, msg_doc.content.text):
                return ResolvedMarker(guild=guild, channel=channel, year=year, message=author_msg, exact=True, source='author')

    # 4 - first message in channel during the year
    first_msg = await _get_message_repo().find_first_message(guild, channel, after, before)
    if first_msg:
        return ResolvedMarker(guild=guild, channel=channel, year=year, message=first_msg, exact=False, source='first')

    # 5 - primary lore channel fallback
    return await _primary_fallback(guild, channel, year)


async def _get_year_window(guild: int, year: int) -> tuple[int, int]:
    """Return (after, before) unix timestamps for a year's window.

    Uses Year records if available, falls back to YearMarker timestamps.
    Returns (0, current_time) as a last resort.
    """
    from nova_core.client.years import Year

    year_record = await Year.get(guild, year)
    if year_record and year_record.start_time > 0:
        after = year_record.start_time
        before = year_record.end_time if year_record.end_time > 0 else int(time.time())
        return after, before

    # fallback to override-based timestamp
    start_marker = await _get_repo().get_any_for_guild_year(guild, year)
    if start_marker:
        after = int(snowflake_time(start_marker.message).timestamp())
        end_marker = await _get_repo().get_any_for_guild_year(guild, year + 1)
        before = int(snowflake_time(end_marker.message).timestamp()) if end_marker else int(time.time())
        return after, before

    return 0, int(time.time())


async def _primary_fallback(guild: int, channel: int, year: int) -> ResolvedMarker:
    """Fall back to the primary lore channel's marker when the target channel has none."""
    try:
        primary_channel_id = config.guild(guild).channels.lore_channels[0]
    except (Exception, IndexError):
        return ResolvedMarker(guild=guild, channel=channel, year=year, message=0, exact=False, source='none')

    if primary_channel_id == channel:
        return ResolvedMarker(guild=guild, channel=channel, year=year, message=0, exact=False, source='none')

    primary = await resolve_marker(guild, primary_channel_id, year)
    if primary.found:
        return ResolvedMarker(guild=guild, channel=channel, year=year, message=primary.message, exact=False, source='primary')

    return ResolvedMarker(guild=guild, channel=channel, year=year, message=0, exact=False, source='none')


# --- Year Marker Override Model ---


class YearMarker(BaseModel):
    """Admin override marker stored in year_markers collection"""

    guild: int
    channel: int
    message: int
    year: int
    exact: bool = True  # overrides are always exact
    wiki_page: bool = False

    async def save(self):
        """Save this override marker to MongoDB"""
        await _get_repo().upsert(
            guild=self.guild,
            channel=self.channel,
            message=self.message,
            year=self.year,
            exact=self.exact,
            wiki_page=self.wiki_page,
        )

    async def update(self, **kwargs):
        """Update specific fields and persist to database"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        await _get_repo().update(self.channel, self.year, **kwargs)

    async def delete(self):
        """Delete this override marker"""
        await _get_repo().delete(self.channel, self.year)

    @classmethod
    async def get(cls, channel: int, year: int) -> 'YearMarker | None':
        """Get override by channel and year"""
        doc = await _get_repo().get(channel, year)
        if doc:
            return cls(guild=doc.guild, channel=doc.channel, message=doc.message, year=doc.year, exact=doc.exact, wiki_page=doc.wiki_page)
        return None

    @classmethod
    async def get_any(cls, guild: int, year: int) -> 'YearMarker | None':
        """Get any override for a guild+year"""
        doc = await _get_repo().get_any_for_guild_year(guild, year)
        if doc:
            return cls(guild=doc.guild, channel=doc.channel, message=doc.message, year=doc.year, exact=doc.exact, wiki_page=doc.wiki_page)
        return None

    @classmethod
    async def total(cls, guild: int | None = None) -> int:
        """Count total override markers for a guild"""
        if guild is None:
            primary = config.get_guild_by_role('primary')
            guild = primary.id if primary is not None else 0
        return await _get_repo().total(guild)

    @classmethod
    async def timestamp(cls, year: int, guild: int | None = None) -> int | None:
        """Get timestamp from an override marker snowflake, or None if no override exists"""
        if guild is None:
            primary = config.get_guild_by_role('primary')
            guild = primary.id if primary is not None else 0

        marker = await _get_repo().get_any_for_guild_year(guild, year)
        if not marker:
            return None
        return int(snowflake_time(marker.message).timestamp())

    @classmethod
    async def mark(cls, year: int, message_id: int, channel: int | None = None, guild: int | None = None):
        """Store a bot rollover message as an exact override marker"""
        primary = config.get_guild_by_role('primary')
        primary_id = primary.id if primary is not None else 0
        if channel is None:
            channel = primary_id  # NOTE: pre-existing bug - channel defaults to guild id; tracked in bugs.md
        if guild is None:
            guild = primary_id

        logger.info(f'marker override stored: guild={guild} channel={channel} year={year} message={message_id}')
        await _get_repo().upsert(guild=guild, channel=channel, year=year, message=message_id, exact=True)

    @classmethod
    async def all_for_guild(cls, guild: int) -> list['YearMarker']:
        """List all override markers for a guild"""
        docs = await _get_repo().all_for_guild(guild)
        return [cls(guild=doc.guild, channel=doc.channel, message=doc.message, year=doc.year, exact=doc.exact, wiki_page=doc.wiki_page) for doc in docs]

    @classmethod
    async def get_or_create(cls, guild: int, channel: int, year: int, message: int) -> tuple['YearMarker', bool]:
        """Get or create an override marker. Returns (marker, created)"""
        doc, created = await _get_repo().get_or_create(guild, channel, year, message)
        marker = cls(guild=doc.guild, channel=doc.channel, message=doc.message, year=doc.year, exact=doc.exact, wiki_page=doc.wiki_page)
        return marker, created

    @classmethod
    async def exists(cls, channel: int, year: int) -> bool:
        """Check if an override exists for the given channel and year"""
        return await _get_repo().exists(channel, year)
