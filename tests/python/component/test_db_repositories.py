# SPDX-License-Identifier: Apache-2.0
"""tests.python.component.test_db_repositories | repository component tests against real MongoDB."""

import os
import time
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import tomlkit

from nova_core.database.models import (
    MessageAuthor,
    MessageContent,
    MessageDocument,
    StarredMessageDocument,
    SystemConfigDocument,
)
from nova_core.database.repositories import (
    ConfigRepository,
    MessageRepository,
    YearMarkerRepository,
    YearRepository,
)
from nova_core.starboard.repositories import StarboardRepository


pytestmark = pytest.mark.component


def _read_db_config() -> tuple[str, str]:
    """read database url and name from the toml config file.

    checks TEST_DB_URL first so the test container needs no secrets mount.
    falls back to unauthenticated localhost for convenience in local dev
    without a config file present.
    """
    if url := os.environ.get('TEST_DB_URL'):
        db_name = url.rsplit('/', 1)[-1].split('?', 1)[0] or 'doombot'
        return url, db_name
    config_path = Path(os.environ.get('ATTU_CONFIG_FILE', './.secrets/attu-bot.toml'))
    if config_path.exists():
        with config_path.open() as f:
            raw = tomlkit.load(f)
        return str(raw['database']['url']), str(raw['database']['name'])  # pyright: ignore[reportIndexIssue]
    return 'mongodb://localhost:27017', 'doombot'


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
    from nova_core.config import GuildCCBoard, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildStarboard, GuildUsers

    return GuildConfig(
        id=guild_id,
        channels=GuildChannels(activity=100, logs=200, lore_channels=[300, 400]),
        epoch=GuildEpoch(time=1704067200, year=3, length=14, paused=False, rollover_minutes=1020),
        roles=GuildRoles(announcements=500),
        users=GuildUsers(markers=[600, 700]),
        starboard=GuildStarboard(channel_id=800, emojis={'⭐': '#EEDD20'}),
        ccboard=GuildCCBoard(
            enabled=True,
            channel_id=900,
            emojis={'⭐': 1, '💀': -1},
            super_bonus=2,
            threshold=3,
            points_label='points',
            positive_color='#00ff00',
            negative_color='#ff0000',
            weights_updated_at=1735689600,  # 2025-01-01 00:00:00 UTC
        ),
    )


def _make_message_doc(message_id=1, guild_id=2222222222, channel_id=3333333333, author_id=4444444444, created_at=None):
    return MessageDocument(
        message_id=message_id,
        guild_id=guild_id,
        channel_id=channel_id,
        author=MessageAuthor(id=author_id, name='TestUser'),
        content=MessageContent(text='hello world'),
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


# --- ConfigRepository ---


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

    async def test_ccboard_roundtrip_through_load_guild(self, db):
        """save a guild with non-default ccboard, reconstruct via the same code path
        load_guild() uses, and assert every ccboard field survives. catches the
        silent-default failure mode where a missing line in load_guild() would cause
        ccboard fields to revert to defaults regardless of the saved document.
        """
        from nova_core.config import GuildCCBoard, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildStarboard, GuildUsers

        repo = ConfigRepository(db)
        await repo.init_indexes()
        cfg = _make_guild_config(guild_id=1234567890)
        await repo.save_guild(cfg)

        doc = await repo.get_guild(1234567890)
        assert doc is not None
        # mirror load_guild's reconstruction step
        reloaded = GuildConfig(
            id=1234567890,
            channels=GuildChannels(**doc.channels),
            epoch=GuildEpoch(**doc.epoch),
            roles=GuildRoles(**doc.roles),
            users=GuildUsers(**doc.users),
            starboard=GuildStarboard(**doc.starboard),
            ccboard=GuildCCBoard(**doc.ccboard),
        )
        assert reloaded.ccboard.enabled is True
        assert reloaded.ccboard.channel_id == 900
        assert reloaded.ccboard.emojis == {'⭐': 1, '💀': -1}
        assert reloaded.ccboard.super_bonus == 2
        assert reloaded.ccboard.threshold == 3
        assert reloaded.ccboard.points_label == 'points'
        assert reloaded.ccboard.positive_color == '#00ff00'
        assert reloaded.ccboard.negative_color == '#ff0000'
        assert reloaded.ccboard.weights_updated_at == 1735689600

    async def test_starboard_enabled_roundtrip_through_load_guild(self, db):
        """save a guild with starboard.enabled=False, reconstruct via the same code path
        load_guild() uses, and assert the value survives. catches the silent-default
        failure mode where a missing line in load_guild() would revert enabled to True.
        """
        from nova_core.config import GuildCCBoard, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildStarboard, GuildUsers

        repo = ConfigRepository(db)
        await repo.init_indexes()
        cfg = GuildConfig(
            id=9876543210,
            channels=GuildChannels(activity=100, logs=200, lore_channels=[]),
            epoch=GuildEpoch(time=1704067200, year=3, length=14, paused=False, rollover_minutes=1020),
            roles=GuildRoles(announcements=500),
            users=GuildUsers(markers=[]),
            starboard=GuildStarboard(enabled=False, channel_id=800, emojis={'⭐': '#EEDD20'}),
            ccboard=GuildCCBoard(),
        )
        await repo.save_guild(cfg)

        doc = await repo.get_guild(9876543210)
        assert doc is not None
        reloaded = GuildConfig(
            id=9876543210,
            channels=GuildChannels(**doc.channels),
            epoch=GuildEpoch(**doc.epoch),
            roles=GuildRoles(**doc.roles),
            users=GuildUsers(**doc.users),
            starboard=GuildStarboard(**doc.starboard),
            ccboard=GuildCCBoard(**doc.ccboard),
        )
        assert reloaded.starboard.enabled is False
        assert reloaded.starboard.channel_id == 800


class TestConfigRepositoryTheme:
    async def test_theme_roundtrip(self, db):
        from nova_core.config import BotTheme

        repo = ConfigRepository(db)
        await repo.init_indexes()
        theme = BotTheme(rotation=90.0, max_rate=0.5, bot_color='#ff0000', guild_color='#00ff00')
        await repo.save_theme(theme)
        doc = await repo.get_theme()
        assert doc is not None
        assert doc.rotation == 90.0
        assert doc.bot_color == '#ff0000'

    async def test_theme_roundtrip_ui_emojis(self, db):
        from nova_core.config import BotTheme

        repo = ConfigRepository(db)
        await repo.init_indexes()
        emojis = {'rockball': 1308981475114225694, 'crackerpeaty': 1214140141245825024}
        theme = BotTheme(rotation=0.0, max_rate=0.5, bot_color='#000000', guild_color='#ffffff', ui_emojis=emojis)
        await repo.save_theme(theme)
        doc = await repo.get_theme()
        assert doc is not None
        assert doc.ui_emojis == emojis

    async def test_theme_upsert(self, db):
        from nova_core.config import BotTheme

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


# --- YearRepository ---


guild = 2222222222


class TestYearRepository:
    async def test_create_and_get(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=1704067200)
        doc = await repo.get(guild, 1)
        assert doc is not None
        assert doc.year == 1
        assert doc.start_time == 1704067200

    async def test_get_missing_returns_none(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        assert await repo.get(guild, 999) is None

    async def test_upsert_idempotent(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.upsert(guild, year=1, start_time=100)
        await repo.upsert(guild, year=1, start_time=200)
        doc = await repo.get(guild, 1)
        assert doc.start_time == 200

    async def test_update_fields(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=1704067200)
        await repo.update(guild, 1, end_time=1705276800, duration=14)
        doc = await repo.get(guild, 1)
        assert doc.end_time == 1705276800
        assert doc.duration == 14

    async def test_delete(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=1704067200)
        await repo.delete(guild, 1)
        assert await repo.get(guild, 1) is None

    async def test_total(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=100)
        await repo.create(guild, year=2, start_time=200)
        assert await repo.total(guild) == 2

    async def test_exists_true_and_false(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=100)
        assert await repo.exists(guild, 1) is True
        assert await repo.exists(guild, 2) is False

    async def test_all_for_guild_sorted(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=3, start_time=300)
        await repo.create(guild, year=1, start_time=100)
        await repo.create(guild, year=2, start_time=200)
        docs = await repo.all_for_guild(guild)
        assert [d.year for d in docs] == [1, 2, 3]

    async def test_all_for_guild_excludes_other_guilds(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=100)
        await repo.create(9999999999, year=1, start_time=100)
        docs = await repo.all_for_guild(guild)
        assert len(docs) == 1

    async def test_get_latest(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=100)
        await repo.create(guild, year=5, start_time=500)
        await repo.create(guild, year=3, start_time=300)
        latest = await repo.get_latest(guild)
        assert latest.year == 5

    async def test_get_latest_empty(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        assert await repo.get_latest(guild) is None

    async def test_get_or_create_creates(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        doc, created = await repo.get_or_create(guild, year=1, start_time=100)
        assert created is True
        assert doc.year == 1

    async def test_get_or_create_returns_existing(self, db):
        repo = YearRepository(db)
        await repo.init_indexes()
        await repo.create(guild, year=1, start_time=100)
        doc, created = await repo.get_or_create(guild, year=1, start_time=999)
        assert created is False
        assert doc.start_time == 100  # not overwritten


# --- YearMarkerRepository ---


channel = 3333333333
marker_guild = 4444444444


class TestYearMarkerRepository:
    async def test_create_and_get(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel=channel, message=100, year=1)
        doc = await repo.get(channel, 1)
        assert doc is not None
        assert doc.message == 100
        assert doc.exact is False

    async def test_get_missing_returns_none(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        assert await repo.get(channel, 999) is None

    async def test_upsert_idempotent(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.upsert(marker_guild, channel, message=100, year=1)
        await repo.upsert(marker_guild, channel, message=200, year=1, exact=True)
        doc = await repo.get(channel, 1)
        assert doc.message == 200
        assert doc.exact is True

    async def test_update(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=1)
        await repo.update(channel, 1, message=999, exact=True)
        doc = await repo.get(channel, 1)
        assert doc.message == 999
        assert doc.exact is True

    async def test_delete(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=1)
        await repo.delete(channel, 1)
        assert await repo.get(channel, 1) is None

    async def test_exists(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=1)
        assert await repo.exists(channel, 1) is True
        assert await repo.exists(channel, 2) is False

    async def test_total(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=1)
        await repo.create(marker_guild, channel + 1, message=200, year=1)
        assert await repo.total(marker_guild) == 2

    async def test_all_for_guild(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=1)
        await repo.create(marker_guild, channel, message=200, year=2)
        docs = await repo.all_for_guild(marker_guild)
        assert len(docs) == 2

    async def test_all_for_guild_excludes_other_guilds(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=1)
        await repo.create(9999999999, channel + 99, message=999, year=1)
        docs = await repo.all_for_guild(marker_guild)
        assert len(docs) == 1

    async def test_get_any_for_guild_year(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=5)
        doc = await repo.get_any_for_guild_year(marker_guild, 5)
        assert doc is not None
        assert doc.year == 5

    async def test_get_any_for_guild_year_missing(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        assert await repo.get_any_for_guild_year(marker_guild, 999) is None

    async def test_get_or_create_creates(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        doc, created = await repo.get_or_create(marker_guild, channel, year=1, message=100)
        assert created is True
        assert doc.message == 100

    async def test_get_or_create_existing(self, db):
        repo = YearMarkerRepository(db)
        await repo.init_indexes()
        await repo.create(marker_guild, channel, message=100, year=1)
        doc, created = await repo.get_or_create(marker_guild, channel, year=1, message=999)
        assert created is False
        assert doc.message == 100  # not overwritten


# --- MessageRepository ---


msg_guild = 5555555555
msg_channel = 6666666666


class TestMessageRepository:
    async def test_upsert_and_get(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=msg_guild, channel_id=msg_channel)
        await repo.upsert(doc)
        result = await repo.get(1)
        assert result is not None
        assert result.content.text == 'hello world'

    async def test_get_missing_returns_none(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.get(999999) is None

    async def test_upsert_overwrites(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=msg_guild, channel_id=msg_channel)
        await repo.upsert(doc)
        doc.content.text = 'updated'
        await repo.upsert(doc)
        result = await repo.get(1)
        assert result.content.text == 'updated'

    async def test_mark_edited(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=msg_guild, channel_id=msg_channel)
        await repo.upsert(doc)
        await repo.mark_edited(1, content='edited text', edited_at=9999)
        result = await repo.get(1)
        assert result.content.text == 'edited text'
        assert result.edited_at == 9999

    async def test_mark_deleted(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        doc = _make_message_doc(message_id=1, guild_id=msg_guild, channel_id=msg_channel)
        await repo.upsert(doc)
        await repo.mark_deleted(1, deleted_at=8888)
        result = await repo.get(1)
        assert result.deleted is True
        assert result.deleted_at == 8888

    async def test_mark_bulk_deleted(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_message_doc(message_id=i, guild_id=msg_guild, channel_id=msg_channel))
        await repo.mark_bulk_deleted([1, 2, 3], deleted_at=7777)
        for i in range(1, 4):
            result = await repo.get(i)
            assert result.deleted is True

    async def test_get_latest_in_channel(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for mid in [10, 30, 20]:
            await repo.upsert(_make_message_doc(message_id=mid, guild_id=msg_guild, channel_id=msg_channel))
        latest = await repo.get_latest_in_channel(msg_guild, msg_channel)
        assert latest == 30

    async def test_get_latest_in_channel_empty(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.get_latest_in_channel(msg_guild, msg_channel) is None

    async def test_count_for_guild(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_message_doc(message_id=i, guild_id=msg_guild, channel_id=msg_channel))
        assert await repo.count_for_guild(msg_guild) == 3

    async def test_count_for_channel(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        ch_a, ch_b = msg_channel, msg_channel + 1
        await repo.upsert(_make_message_doc(message_id=1, guild_id=msg_guild, channel_id=ch_a))
        await repo.upsert(_make_message_doc(message_id=2, guild_id=msg_guild, channel_id=ch_b))
        assert await repo.count_for_channel(msg_guild, ch_a) == 1
        assert await repo.count_for_channel(msg_guild, ch_b) == 1

    async def test_distinct_author_ids(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i, author in enumerate([100, 200, 100], start=1):
            doc = _make_message_doc(message_id=i, guild_id=msg_guild, channel_id=msg_channel, author_id=author)
            await repo.upsert(doc)
        ids = await repo.distinct_author_ids(msg_guild)
        assert set(ids) == {100, 200}

    async def test_update_author_name(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 3):
            doc = _make_message_doc(message_id=i, guild_id=msg_guild, channel_id=msg_channel, author_id=100)
            await repo.upsert(doc)
        count = await repo.update_author_name(100, 'NewName')
        assert count == 2
        result = await repo.get(1)
        assert result.author.name == 'NewName'

    async def test_find_bot_header(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        t = int(time.time())
        doc = MessageDocument(
            message_id=1,
            guild_id=msg_guild,
            channel_id=msg_channel,
            author=MessageAuthor(id=0, name='Bot', bot=True),
            content=MessageContent(text='Year 5 begins'),
            created_at=t,
        )
        await repo.upsert(doc)
        result = await repo.find_bot_header(msg_guild, msg_channel, 'Year 5', after=t - 1, before=t + 100)
        assert result == 1

    async def test_find_bot_header_no_match(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.find_bot_header(msg_guild, msg_channel, 'Year 5', after=0, before=1) is None

    async def test_find_author_message(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        t = int(time.time())
        doc = _make_message_doc(message_id=1, guild_id=msg_guild, channel_id=msg_channel, author_id=999, created_at=t)
        await repo.upsert(doc)
        result = await repo.find_author_message(msg_guild, msg_channel, [999], after=t - 1, before=t + 100)
        assert result == 1

    async def test_find_author_message_empty_ids(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        assert await repo.find_author_message(msg_guild, msg_channel, [], after=0, before=999999999999) is None

    async def test_find_first_message(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        t = int(time.time())
        for i, delta in enumerate([5, 0, 10], start=1):
            doc = _make_message_doc(message_id=i, guild_id=msg_guild, channel_id=msg_channel, created_at=t + delta)
            await repo.upsert(doc)
        result = await repo.find_first_message(msg_guild, msg_channel, after=t - 1, before=t + 100)
        # message_id=2 was created at t+0 = earliest
        assert result == 2

    async def test_get_all_message_ids_in_channel(self, db):
        repo = MessageRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_message_doc(message_id=i, guild_id=msg_guild, channel_id=msg_channel))
        ids = await repo.get_all_message_ids_in_channel(msg_guild, msg_channel)
        assert ids == {1, 2, 3}


# --- StarboardRepository ---


sb_guild = 7777777777
sb_channel = 8888888888


class TestStarboardRepository:
    async def test_upsert_and_get(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = _make_star_doc(message_id=1, guild_id=sb_guild, channel_id=sb_channel)
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
        doc = _make_star_doc(message_id=1, guild_id=sb_guild, channel_id=sb_channel)
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
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10)
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
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10)
        await repo.upsert(doc)
        await repo.add_reaction(1, '⭐', user_id=99)
        await repo.add_reaction(1, '⭐', user_id=99)
        result = await repo.get(1)
        assert result.reactions['⭐'].count(99) == 1

    async def test_add_super_reaction(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10)
        await repo.upsert(doc)
        result = await repo.add_super_reaction(1, '⭐', user_id=99)
        assert 99 in result.super_reactions.get('⭐', [])

    async def test_add_super_reaction_removes_normal(self, db):
        """adding a super reaction should evict the same user from normal reactions"""
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, reactions={'⭐': [99]})
        await repo.upsert(doc)
        result = await repo.add_super_reaction(1, '⭐', user_id=99)
        assert 99 not in result.reactions.get('⭐', [])
        assert 99 in result.super_reactions.get('⭐', [])

    async def test_remove_reaction(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, reactions={'⭐': [1, 2, 3]}, total_reactions=3)
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
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, super_reactions={'⭐': [99]}, total_reactions=1, weighted_total=1.5)
        await repo.upsert(doc)
        result = await repo.remove_super_reaction(1, '⭐', user_id=99)
        assert 99 not in result.super_reactions.get('⭐', [])

    async def test_set_starboard_message(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = _make_star_doc(message_id=1, guild_id=sb_guild, channel_id=sb_channel)
        await repo.upsert(doc)
        await repo.set_starboard_message(1, 42)
        result = await repo.get(1)
        assert result.starboard_message_id == 42

    async def test_set_starboard_message_unlink(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = _make_star_doc(message_id=1, guild_id=sb_guild, channel_id=sb_channel)
        await repo.upsert(doc)
        await repo.set_starboard_message(1, 42)
        await repo.set_starboard_message(1, None)
        result = await repo.get(1)
        assert result.starboard_message_id is None

    async def test_total_for_guild(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        for i in range(1, 4):
            await repo.upsert(_make_star_doc(message_id=i, guild_id=sb_guild, channel_id=sb_channel))
        assert await repo.total_for_guild(sb_guild) == 3

    async def test_sum_reactions_for_guild(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc1 = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, total_reactions=5, weighted_total=5.0)
        doc2 = StarredMessageDocument(message_id=2, channel_id=sb_channel, guild_id=sb_guild, author_id=10, total_reactions=3, weighted_total=3.0)
        await repo.upsert(doc1)
        await repo.upsert(doc2)
        total = await repo.sum_reactions_for_guild(sb_guild)
        assert total == 8

    async def test_all_for_guild(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        for i in range(1, 3):
            await repo.upsert(_make_star_doc(message_id=i, guild_id=sb_guild, channel_id=sb_channel))
        docs = await repo.all_for_guild(sb_guild)
        assert len(docs) == 2

    async def test_leaderboard_most_stars(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        # author 10 has 3 stars, author 20 has 5
        doc1 = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, reactions={'⭐': [1, 2, 3]})
        doc2 = StarredMessageDocument(message_id=2, channel_id=sb_channel, guild_id=sb_guild, author_id=20, reactions={'⭐': [1, 2, 3, 4, 5]})
        await repo.upsert(doc1)
        await repo.upsert(doc2)
        rows = await repo.leaderboard_most_stars(sb_guild)
        assert rows[0]['_id'] == 20
        assert rows[0]['total_stars'] == 5

    async def test_leaderboard_most_starred(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc1 = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, starboard_message_id=100)
        doc2 = StarredMessageDocument(message_id=2, channel_id=sb_channel, guild_id=sb_guild, author_id=10, starboard_message_id=200)
        doc3 = StarredMessageDocument(message_id=3, channel_id=sb_channel, guild_id=sb_guild, author_id=20, starboard_message_id=None)
        await repo.upsert(doc1)
        await repo.upsert(doc2)
        await repo.upsert(doc3)
        rows = await repo.leaderboard_most_starred(sb_guild)
        assert rows[0]['_id'] == 10
        assert rows[0]['starred_messages'] == 2

    async def test_leaderboard_most_given(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, reactions={'⭐': [1, 2, 3]})
        await repo.upsert(doc)
        rows = await repo.leaderboard_most_given(sb_guild)
        assert len(rows) == 3

    async def test_get_random(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, total_reactions=5)
        await repo.upsert(doc)
        result = await repo.get_random(sb_guild, min_total=1)
        assert result is not None
        assert result.message_id == 1

    async def test_get_random_no_match(self, db):
        repo = StarboardRepository(db)
        await repo.init_indexes()
        result = await repo.get_random(sb_guild, min_total=99)
        assert result is None

    async def test_total_synced_after_add_reaction(self, db):
        """_sync_totals should correct drifted total_reactions on the stored doc"""
        repo = StarboardRepository(db)
        await repo.init_indexes()
        # store a doc with deliberately wrong totals
        doc = StarredMessageDocument(message_id=1, channel_id=sb_channel, guild_id=sb_guild, author_id=10, reactions={'⭐': []}, total_reactions=99, weighted_total=99.0)
        await repo.upsert(doc)
        result = await repo.add_reaction(1, '⭐', user_id=1)
        # total should now be 1, not 99
        assert result.total_reactions == 1
