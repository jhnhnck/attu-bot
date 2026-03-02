"""
AttuBot - Repository Component Tests (real MongoDB)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

These tests run against a real MongoDB instance.  In docker-compose the service
is reachable at mongodb://mongo:27017; locally it falls back to localhost.
"""

import os
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import tomlkit

from attubot.database.models import (
    MessageDocument,
    StarredMessageDocument,
    SystemConfigDocument,
)
from attubot.database.repositories import (
    ConfigRepository,
    MessageRepository,
    ReloadSignalRepository,
    StarboardRepository,
    YearMarkerRepository,
    YearRepository,
)

pytestmark = pytest.mark.component


def _read_db_config() -> tuple[str, str]:
    """read database url and name from the toml config file.

    falls back to unauthenticated localhost for convenience in local dev
    without a config file present.
    """
    config_path = Path(os.environ.get('ATTU_CONFIG_FILE', './assets/attu-bot.toml'))
    if config_path.exists():
        with config_path.open() as f:
            raw = tomlkit.load(f)
        return raw['database']['url'], raw['database']['name']
    return 'mongodb://mongo:27017', 'doombot'


class _PrefixedDB:
    """wraps a pymongo AsyncDatabase and prepends a per-test prefix to every
    collection name so tests are isolated without needing a separate database
    (which requires admin/dropDatabase privileges)."""

    def __init__(self, real_db, prefix: str):
        self._db = real_db
        self._prefix = prefix
        self._used: list[str] = []

    def __getitem__(self, name: str):
        prefixed = f'{self._prefix}_{name}'
        if prefixed not in self._used:
            self._used.append(prefixed)
        return self._db[prefixed]

    def __getattr__(self, name: str):
        return getattr(self._db, name)

    async def cleanup(self):
        for col in self._used:
            await self._db[col].drop()


# --- shared db fixture ---


@pytest_asyncio.fixture
async def db():
    """connect to the live mongodb and wrap it with a per-test collection prefix.

    uses the same url/db as the application so credentials are handled correctly.
    each test gets uniquely-named collections that are dropped at teardown -
    no dropDatabase required.
    """
    from pymongo import AsyncMongoClient

    url, db_name = _read_db_config()
    client = AsyncMongoClient(url, serverSelectionTimeoutMS=5000)
    prefix = f'test_{uuid.uuid4().hex[:10]}'
    wrapped = _PrefixedDB(client[db_name], prefix)
    yield wrapped
    await wrapped.cleanup()
    await client.close()


# --- helper factories ---


def _make_guild_config(guild_id: int = 1111111111):
    """return a minimal GuildConfig-like object for repo tests"""
    from attubot.config import GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildStarboard, GuildUsers

    return GuildConfig(
        id=guild_id,
        channels=GuildChannels(activity=100, logs=200, lore_channels=[300, 400]),
        epoch=GuildEpoch(time=1704067200, year=3, length=14, paused=False, rollover_minutes=1020),
        roles=GuildRoles(announcements=500),
        users=GuildUsers(markers=[600, 700]),
        starboard=GuildStarboard(channel_id=800, emojis={'⭐': '#EEDD20'}),
    )


def _make_message_doc(message_id=1, guild_id=2222222222, channel_id=3333333333, author_id=4444444444, created_at=None):
    return MessageDocument(
        message_id=message_id,
        guild_id=guild_id,
        channel_id=channel_id,
        author_id=author_id,
        author_name='TestUser',
        content='hello world',
        created_at=created_at or int(time.time()),
    )


def _make_star_doc(message_id=1, guild_id=2222222222, channel_id=3333333333, author_id=4444444444):
    return StarredMessageDocument(
        message_id=message_id,
        channel_id=channel_id,
        guild_id=guild_id,
        author_id=author_id,
        reactions={'⭐': [1, 2, 3]},
        total_reactions=3,
        weighted_total=3.0,
    )


# ============================================================
# ConfigRepository
# ============================================================


class TestConfigRepositoryIndexes:
    async def test_guild_unique_index(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        cfg = _make_guild_config()
        await repo.save_guild(cfg)
        # second upsert should not raise
        await repo.save_guild(cfg)

    async def test_global_unique_index(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        system = SystemConfigDocument(version='1.0.0', error_log=[0, 0], error_hook='http://x', primary_guild=0)
        await repo.save_system(system)
        await repo.save_system(system)  # idempotent


class TestConfigRepositoryGuild:
    async def test_roundtrip(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        cfg = _make_guild_config(guild_id=1111111111)
        await repo.save_guild(cfg)
        doc = await repo.get_guild(1111111111)
        assert doc is not None
        assert doc.guild_id == 1111111111
        assert doc.channels['activity'] == 100
        assert doc.epoch['year'] == 3

    async def test_get_missing_returns_none(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        assert await repo.get_guild(9999999999) is None

    async def test_update_field(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        cfg = _make_guild_config()
        await repo.save_guild(cfg)
        await repo.update_guild_field(cfg.id, 'epoch.year', 99)
        doc = await repo.get_guild(cfg.id)
        assert doc.epoch['year'] == 99

    async def test_upsert_overwrites(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        cfg = _make_guild_config()
        await repo.save_guild(cfg)
        cfg.epoch.year = 7
        await repo.save_guild(cfg)
        doc = await repo.get_guild(cfg.id)
        assert doc.epoch['year'] == 7


class TestConfigRepositoryTheme:
    async def test_theme_roundtrip(self, db):
        from attubot.config import BotTheme

        repo = ConfigRepository(db)
        await repo.init_indexes()
        theme = BotTheme(rotation=90.0, max_rate=0.5, bot_color='#ff0000', guild_color='#00ff00')
        await repo.save_theme(theme)
        doc = await repo.get_theme()
        assert doc is not None
        assert doc.rotation == 90.0
        assert doc.bot_color == '#ff0000'

    async def test_theme_upsert(self, db):
        from attubot.config import BotTheme

        repo = ConfigRepository(db)
        await repo.init_indexes()
        await repo.save_theme(BotTheme(rotation=0.0, max_rate=0.5, bot_color='#ff0000', guild_color='#ffffff'))
        await repo.save_theme(BotTheme(rotation=45.0, max_rate=0.8, bot_color='#0000ff', guild_color='#ffff00'))
        doc = await repo.get_theme()
        assert doc.rotation == 45.0
        assert doc.bot_color == '#0000ff'

    async def test_get_theme_missing_returns_none(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        assert await repo.get_theme() is None


class TestConfigRepositorySystem:
    async def test_system_roundtrip(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        system = SystemConfigDocument(version='2.4.4', error_log=[111, 222], error_hook='https://x', primary_guild=111)
        await repo.save_system(system)
        doc = await repo.get_system()
        assert doc is not None
        assert doc.version == '2.4.4'
        assert doc.error_log == [111, 222]

    async def test_update_system_field(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        system = SystemConfigDocument(version='2.0.0', error_log=[0, 0], error_hook='https://x', primary_guild=0)
        await repo.save_system(system)
        await repo.update_system_field('version', '2.4.4')
        doc = await repo.get_system()
        assert doc.version == '2.4.4'

    async def test_get_system_missing_returns_none(self, db):
        repo = ConfigRepository(db)
        await repo.init_indexes()
        assert await repo.get_system() is None


# ============================================================
# YearRepository
# ============================================================


GUILD = 2222222222


class TestYearRepository:
    async def test_create_and_get(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=1704067200)
        doc = await repo.get(GUILD, 1)
        assert doc is not None
        assert doc.year == 1
        assert doc.start_time == 1704067200

    async def test_get_missing_returns_none(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        assert await repo.get(GUILD, 999) is None

    async def test_upsert_idempotent(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.upsert(GUILD, year=1, start_time=100)
        await repo.upsert(GUILD, year=1, start_time=200)
        doc = await repo.get(GUILD, 1)
        assert doc.start_time == 200

    async def test_update_fields(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=1704067200)
        await repo.update(GUILD, 1, end_time=1705276800, duration=14)
        doc = await repo.get(GUILD, 1)
        assert doc.end_time == 1705276800
        assert doc.duration == 14

    async def test_delete(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=1704067200)
        await repo.delete(GUILD, 1)
        assert await repo.get(GUILD, 1) is None

    async def test_total(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=100)
        await repo.create(GUILD, year=2, start_time=200)
        assert await repo.total(GUILD) == 2

    async def test_exists_true_and_false(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=100)
        assert await repo.exists(GUILD, 1) is True
        assert await repo.exists(GUILD, 2) is False

    async def test_all_for_guild_sorted(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=3, start_time=300)
        await repo.create(GUILD, year=1, start_time=100)
        await repo.create(GUILD, year=2, start_time=200)
        docs = await repo.all_for_guild(GUILD)
        assert [d.year for d in docs] == [1, 2, 3]

    async def test_all_for_guild_excludes_other_guilds(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=100)
        await repo.create(9999999999, year=1, start_time=100)
        docs = await repo.all_for_guild(GUILD)
        assert len(docs) == 1

    async def test_get_latest(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=100)
        await repo.create(GUILD, year=5, start_time=500)
        await repo.create(GUILD, year=3, start_time=300)
        latest = await repo.get_latest(GUILD)
        assert latest.year == 5

    async def test_get_latest_empty(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        assert await repo.get_latest(GUILD) is None

    async def test_get_or_create_creates(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        doc, created = await repo.get_or_create(GUILD, year=1, start_time=100)
        assert created is True
        assert doc.year == 1

    async def test_get_or_create_returns_existing(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(GUILD, year=1, start_time=100)
        doc, created = await repo.get_or_create(GUILD, year=1, start_time=999)
        assert created is False
        assert doc.start_time == 100  # not overwritten


# ============================================================
# YearMarkerRepository
# ============================================================


CHANNEL = 3333333333
MARKER_GUILD = 4444444444


class TestYearMarkerRepository:
    async def test_create_and_get(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, channel=CHANNEL, message=100, year=1)
        doc = await repo.get(CHANNEL, 1)
        assert doc is not None
        assert doc.message == 100
        assert doc.exact is False

    async def test_get_missing_returns_none(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        assert await repo.get(CHANNEL, 999) is None

    async def test_upsert_idempotent(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.upsert(MARKER_GUILD, CHANNEL, message=100, year=1)
        await repo.upsert(MARKER_GUILD, CHANNEL, message=200, year=1, exact=True)
        doc = await repo.get(CHANNEL, 1)
        assert doc.message == 200
        assert doc.exact is True

    async def test_update(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=1)
        await repo.update(CHANNEL, 1, message=999, exact=True)
        doc = await repo.get(CHANNEL, 1)
        assert doc.message == 999
        assert doc.exact is True

    async def test_delete(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=1)
        await repo.delete(CHANNEL, 1)
        assert await repo.get(CHANNEL, 1) is None

    async def test_exists(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=1)
        assert await repo.exists(CHANNEL, 1) is True
        assert await repo.exists(CHANNEL, 2) is False

    async def test_total(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=1)
        await repo.create(MARKER_GUILD, CHANNEL + 1, message=200, year=1)
        assert await repo.total(MARKER_GUILD) == 2

    async def test_all_for_guild(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=1)
        await repo.create(MARKER_GUILD, CHANNEL, message=200, year=2)
        docs = await repo.all_for_guild(MARKER_GUILD)
        assert len(docs) == 2

    async def test_all_for_guild_excludes_other_guilds(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=1)
        await repo.create(9999999999, CHANNEL + 99, message=999, year=1)
        docs = await repo.all_for_guild(MARKER_GUILD)
        assert len(docs) == 1

    async def test_get_any_for_guild_year(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=5)
        doc = await repo.get_any_for_guild_year(MARKER_GUILD, 5)
        assert doc is not None
        assert doc.year == 5

    async def test_get_any_for_guild_year_missing(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        assert await repo.get_any_for_guild_year(MARKER_GUILD, 999) is None

    async def test_get_or_create_creates(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        doc, created = await repo.get_or_create(MARKER_GUILD, CHANNEL, year=1, message=100)
        assert created is True
        assert doc.message == 100

    async def test_get_or_create_existing(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(MARKER_GUILD, CHANNEL, message=100, year=1)
        doc, created = await repo.get_or_create(MARKER_GUILD, CHANNEL, year=1, message=999)
        assert created is False
        assert doc.message == 100  # not overwritten


# ============================================================
# MessageRepository
# ============================================================


MSG_GUILD = 5555555555
MSG_CHANNEL = 6666666666


class TestMessageRepository:
    async def test_upsert_and_get(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL)
        await repo.upsert(doc)
        result = await repo.get(1)
        assert result is not None
        assert result.content == 'hello world'

    async def test_get_missing_returns_none(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.get(999999) is None

    async def test_upsert_overwrites(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL)
        await repo.upsert(doc)
        doc.content = 'updated'
        await repo.upsert(doc)
        result = await repo.get(1)
        assert result.content == 'updated'

    async def test_mark_edited(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL)
        await repo.upsert(doc)
        await repo.mark_edited(1, content='edited text', edited_at=9999)
        result = await repo.get(1)
        assert result.content == 'edited text'
        assert result.edited_at == 9999

    async def test_mark_deleted(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL)
        await repo.upsert(doc)
        await repo.mark_deleted(1, deleted_at=8888)
        result = await repo.get(1)
        assert result.deleted is True
        assert result.deleted_at == 8888

    async def test_mark_bulk_deleted(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_message_doc(message_id=i, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL))
        await repo.mark_bulk_deleted([1, 2, 3], deleted_at=7777)
        for i in range(1, 4):
            result = await repo.get(i)
            assert result.deleted is True

    async def test_get_latest_in_channel(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for mid in [10, 30, 20]:
            await repo.upsert(_make_message_doc(message_id=mid, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL))
        latest = await repo.get_latest_in_channel(MSG_GUILD, MSG_CHANNEL)
        assert latest == 30

    async def test_get_latest_in_channel_empty(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.get_latest_in_channel(MSG_GUILD, MSG_CHANNEL) is None

    async def test_count_for_guild(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_message_doc(message_id=i, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL))
        assert await repo.count_for_guild(MSG_GUILD) == 3

    async def test_count_for_channel(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        ch_a, ch_b = MSG_CHANNEL, MSG_CHANNEL + 1
        await repo.upsert(_make_message_doc(message_id=1, guild_id=MSG_GUILD, channel_id=ch_a))
        await repo.upsert(_make_message_doc(message_id=2, guild_id=MSG_GUILD, channel_id=ch_b))
        assert await repo.count_for_channel(MSG_GUILD, ch_a) == 1
        assert await repo.count_for_channel(MSG_GUILD, ch_b) == 1

    async def test_distinct_author_ids(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i, author in enumerate([100, 200, 100], start=1):
            doc = _make_message_doc(message_id=i, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL, author_id=author)
            await repo.upsert(doc)
        ids = await repo.distinct_author_ids(MSG_GUILD)
        assert set(ids) == {100, 200}

    async def test_update_author_name(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 3):
            doc = _make_message_doc(message_id=i, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL, author_id=100)
            await repo.upsert(doc)
        count = await repo.update_author_name(100, 'NewName')
        assert count == 2
        result = await repo.get(1)
        assert result.author_name == 'NewName'

    async def test_find_bot_header(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        t = int(time.time())
        doc = MessageDocument(
            message_id=1,
            guild_id=MSG_GUILD,
            channel_id=MSG_CHANNEL,
            author_id=0,
            author_name='Bot',
            author_bot=True,
            content='Year 5 begins',
            created_at=t,
        )
        await repo.upsert(doc)
        result = await repo.find_bot_header(MSG_GUILD, MSG_CHANNEL, 'Year 5', after=t - 1, before=t + 100)
        assert result == 1

    async def test_find_bot_header_no_match(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.find_bot_header(MSG_GUILD, MSG_CHANNEL, 'Year 5', after=0, before=1) is None

    async def test_find_author_message(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        t = int(time.time())
        doc = _make_message_doc(message_id=1, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL, author_id=999, created_at=t)
        await repo.upsert(doc)
        result = await repo.find_author_message(MSG_GUILD, MSG_CHANNEL, [999], after=t - 1, before=t + 100)
        assert result == 1

    async def test_find_author_message_empty_ids(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.find_author_message(MSG_GUILD, MSG_CHANNEL, [], after=0, before=999999999999) is None

    async def test_find_first_message(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        t = int(time.time())
        for i, delta in enumerate([5, 0, 10], start=1):
            doc = _make_message_doc(message_id=i, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL, created_at=t + delta)
            await repo.upsert(doc)
        result = await repo.find_first_message(MSG_GUILD, MSG_CHANNEL, after=t - 1, before=t + 100)
        # message_id=2 was created at t+0 = earliest
        assert result == 2

    async def test_get_all_message_ids_in_channel(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_message_doc(message_id=i, guild_id=MSG_GUILD, channel_id=MSG_CHANNEL))
        ids = await repo.get_all_message_ids_in_channel(MSG_GUILD, MSG_CHANNEL)
        assert ids == {1, 2, 3}


# ============================================================
# StarboardRepository
# ============================================================


SB_GUILD = 7777777777
SB_CHANNEL = 8888888888


class TestStarboardRepository:
    async def test_upsert_and_get(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = _make_star_doc(message_id=1, guild_id=SB_GUILD, channel_id=SB_CHANNEL)
        await repo.upsert(doc)
        result = await repo.get(1)
        assert result is not None
        assert result.total_reactions == 3

    async def test_get_missing_returns_none(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        assert await repo.get(999) is None

    async def test_get_by_starboard_message(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = _make_star_doc(message_id=1, guild_id=SB_GUILD, channel_id=SB_CHANNEL)
        await repo.upsert(doc)
        await repo.set_starboard_message(1, starboard_message_id=42)
        result = await repo.get_by_starboard_message(42)
        assert result is not None
        assert result.message_id == 1

    async def test_get_by_starboard_message_missing(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        assert await repo.get_by_starboard_message(999) is None

    async def test_add_reaction(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10)
        await repo.upsert(doc)
        result = await repo.add_reaction(1, '⭐', user_id=99)
        assert 99 in result.reactions.get('⭐', [])
        assert result.total_reactions == 1

    async def test_add_reaction_not_found_returns_none(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        assert await repo.add_reaction(999, '⭐', user_id=1) is None

    async def test_add_reaction_deduplicates(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10)
        await repo.upsert(doc)
        await repo.add_reaction(1, '⭐', user_id=99)
        await repo.add_reaction(1, '⭐', user_id=99)
        result = await repo.get(1)
        assert result.reactions['⭐'].count(99) == 1

    async def test_add_super_reaction(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10)
        await repo.upsert(doc)
        result = await repo.add_super_reaction(1, '⭐', user_id=99)
        assert 99 in result.super_reactions.get('⭐', [])

    async def test_add_super_reaction_removes_normal(self, db):
        """adding a super reaction should evict the same user from normal reactions"""
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, reactions={'⭐': [99]})
        await repo.upsert(doc)
        result = await repo.add_super_reaction(1, '⭐', user_id=99)
        assert 99 not in result.reactions.get('⭐', [])
        assert 99 in result.super_reactions.get('⭐', [])

    async def test_remove_reaction(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, reactions={'⭐': [1, 2, 3]}, total_reactions=3)
        await repo.upsert(doc)
        result = await repo.remove_reaction(1, '⭐', user_id=2)
        assert 2 not in result.reactions.get('⭐', [])
        assert result.total_reactions == 2

    async def test_remove_reaction_not_found_returns_none(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        assert await repo.remove_reaction(999, '⭐', user_id=1) is None

    async def test_remove_super_reaction(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, super_reactions={'⭐': [99]}, total_reactions=1, weighted_total=1.5)
        await repo.upsert(doc)
        result = await repo.remove_super_reaction(1, '⭐', user_id=99)
        assert 99 not in result.super_reactions.get('⭐', [])

    async def test_set_starboard_message(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = _make_star_doc(message_id=1, guild_id=SB_GUILD, channel_id=SB_CHANNEL)
        await repo.upsert(doc)
        await repo.set_starboard_message(1, 42)
        result = await repo.get(1)
        assert result.starboard_message_id == 42

    async def test_set_starboard_message_unlink(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = _make_star_doc(message_id=1, guild_id=SB_GUILD, channel_id=SB_CHANNEL)
        await repo.upsert(doc)
        await repo.set_starboard_message(1, 42)
        await repo.set_starboard_message(1, None)
        result = await repo.get(1)
        assert result.starboard_message_id is None

    async def test_total_for_guild(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_star_doc(message_id=i, guild_id=SB_GUILD, channel_id=SB_CHANNEL))
        assert await repo.total_for_guild(SB_GUILD) == 3

    async def test_sum_reactions_for_guild(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc1 = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, total_reactions=5, weighted_total=5.0)
        doc2 = StarredMessageDocument(message_id=2, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, total_reactions=3, weighted_total=3.0)
        await repo.upsert(doc1)
        await repo.upsert(doc2)
        total = await repo.sum_reactions_for_guild(SB_GUILD)
        assert total == 8

    async def test_all_for_guild(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        for i in range(1, 3):
            await repo.upsert(_make_star_doc(message_id=i, guild_id=SB_GUILD, channel_id=SB_CHANNEL))
        docs = await repo.all_for_guild(SB_GUILD)
        assert len(docs) == 2

    async def test_leaderboard_most_stars(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        # author 10 has 3 stars, author 20 has 5
        doc1 = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, reactions={'⭐': [1, 2, 3]})
        doc2 = StarredMessageDocument(message_id=2, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=20, reactions={'⭐': [1, 2, 3, 4, 5]})
        await repo.upsert(doc1)
        await repo.upsert(doc2)
        rows = await repo.leaderboard_most_stars(SB_GUILD)
        assert rows[0]['_id'] == 20
        assert rows[0]['total_stars'] == 5

    async def test_leaderboard_most_starred(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc1 = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, starboard_message_id=100)
        doc2 = StarredMessageDocument(message_id=2, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, starboard_message_id=200)
        doc3 = StarredMessageDocument(message_id=3, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=20, starboard_message_id=None)
        await repo.upsert(doc1)
        await repo.upsert(doc2)
        await repo.upsert(doc3)
        rows = await repo.leaderboard_most_starred(SB_GUILD)
        assert rows[0]['_id'] == 10
        assert rows[0]['starred_messages'] == 2

    async def test_leaderboard_most_given(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, reactions={'⭐': [1, 2, 3]})
        await repo.upsert(doc)
        rows = await repo.leaderboard_most_given(SB_GUILD)
        assert len(rows) == 3

    async def test_get_random(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, total_reactions=5)
        await repo.upsert(doc)
        result = await repo.get_random(SB_GUILD, min_total=1)
        assert result is not None
        assert result.message_id == 1

    async def test_get_random_no_match(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        result = await repo.get_random(SB_GUILD, min_total=99)
        assert result is None

    async def test_total_synced_after_add_reaction(self, db):
        """_sync_totals should correct drifted total_reactions on the stored doc"""
        repo = StarboardRepository(db)
        await repo.init_indexes()
        # store a doc with deliberately wrong totals
        doc = StarredMessageDocument(message_id=1, channel_id=SB_CHANNEL, guild_id=SB_GUILD, author_id=10, reactions={'⭐': []}, total_reactions=99, weighted_total=99.0)
        await repo.upsert(doc)
        result = await repo.add_reaction(1, '⭐', user_id=1)
        # total should now be 1, not 99
        assert result.total_reactions == 1


# ============================================================
# ReloadSignalRepository
# ============================================================


class TestReloadSignalRepository:
    async def test_send_and_consume(self, db):
        repo = ReloadSignalRepository(db)
        await repo.init_indexes()
        await repo.send('guild', guild_id=1111111111)
        signals = await repo.consume_all()
        assert len(signals) == 1
        assert signals[0].signal_type == 'guild'
        assert signals[0].guild_id == 1111111111

    async def test_consume_deletes_signals(self, db):
        repo = ReloadSignalRepository(db)
        await repo.init_indexes()
        await repo.send('theme')
        await repo.consume_all()
        signals = await repo.consume_all()
        assert signals == []

    async def test_coalesces_duplicate_signals(self, db):
        """rapid sends of same (type, guild) should produce only one document"""
        repo = ReloadSignalRepository(db)
        await repo.init_indexes()
        await repo.send('guild', guild_id=1111111111)
        await repo.send('guild', guild_id=1111111111)
        await repo.send('guild', guild_id=1111111111)
        signals = await repo.consume_all()
        assert len(signals) == 1

    async def test_different_guilds_separate_signals(self, db):
        repo = ReloadSignalRepository(db)
        await repo.init_indexes()
        await repo.send('guild', guild_id=1111111111)
        await repo.send('guild', guild_id=2222222222)
        signals = await repo.consume_all()
        assert len(signals) == 2

    async def test_consume_empty_returns_empty_list(self, db):
        repo = ReloadSignalRepository(db)
        await repo.init_indexes()
        assert await repo.consume_all() == []

    async def test_send_system_signal(self, db):
        repo = ReloadSignalRepository(db)
        await repo.init_indexes()
        await repo.send('system')
        signals = await repo.consume_all()
        assert signals[0].signal_type == 'system'
        assert signals[0].guild_id is None
