"""
AttuBot - Shared Test Fixtures
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests run with TZ=UTC so that datetime.fromtimestamp() and _config.timezone are consistent.
"""

import os
import time as _time
import uuid
from pathlib import Path


# Set timezone before any attubot imports (NovaConfig reads TZ in __init__)
os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import tomlkit

from attubot import config
from attubot.config import GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers


TEST_GUILD = 1234567890
TEST_USER = 9876543210
TEST_CHANNEL = 5555555555


@pytest.fixture(autouse=True)
def restore_config_state():
    """Restore the config singleton state after each test.

    Several fixtures mutate the global config singleton (replacing load_guild,
    load_globals, config_repo, guilds, authorized_guilds, setting the init event)
    without teardown. This fixture prevents those mutations from bleeding into
    later tests (notably test_startup_integration and test_task_reload_watcher_component).
    """
    # shallow snapshot of instance attrs
    # avoid restoring loop-bound repo/client objects across tests
    skip_restore_keys = {'config_repo'}
    saved_attrs = {k: v for k, v in vars(config).items() if k not in skip_restore_keys}
    # copy mutable collections that many tests mutate in-place
    saved_guilds = dict(config.guilds)
    saved_authorized_guilds = set(config.authorized_guilds)
    saved_valid_guilds = list(config.valid_guilds)
    saved_owner_ids = set(config.owner_ids)
    # event states must be saved separately - the events dict is mutated in-place
    saved_events = {k: v.is_set() for k, v in config._events.items()}

    yield

    # remove any instance attrs added during the test (e.g. load_guild=AsyncMock())
    for key in list(vars(config)):
        if key not in saved_attrs and key not in skip_restore_keys:
            delattr(config, key)

    # restore any attrs that were replaced (identified by object identity)
    for key, val in saved_attrs.items():
        if vars(config).get(key) is not val:
            setattr(config, key, val)

    # restore in-place mutable state
    config.guilds.clear()
    config.guilds.update(saved_guilds)
    config.authorized_guilds.clear()
    config.authorized_guilds.update(saved_authorized_guilds)
    config.valid_guilds[:] = saved_valid_guilds
    config.owner_ids.clear()
    config.owner_ids.update(saved_owner_ids)

    # clear repo/db handles that may be bound to a different event loop
    config.config_repo = None
    from attubot import db

    db.client = None
    db.db = None

    # restore event set/clear states
    for k, was_set in saved_events.items():
        ev = config._events.get(k)
        if ev is None:
            continue
        if was_set and not ev.is_set():
            ev.set()
        elif not was_set and ev.is_set():
            ev.clear()


@pytest.fixture
def make_guild():
    """Factory fixture: creates a GuildConfig with a custom epoch and registers it in config."""
    created = []

    def _make(guild_id=TEST_GUILD, **epoch_kwargs):
        defaults = {
            'time': 1704067200,  # 2024-01-01 00:00:00 UTC
            'year': 1,
            'length': 14,
            'paused': False,
            'rollover_minutes': 1020,  # 17:00
        }
        defaults.update(epoch_kwargs)

        cfg = GuildConfig(
            id=guild_id,
            channels=GuildChannels(),
            epoch=GuildEpoch(**defaults),
            roles=GuildRoles(),
            users=GuildUsers(),
        )

        config.guilds[guild_id] = cfg
        config.authorized_guilds.add(guild_id)
        if guild_id not in config.valid_guilds:
            config.valid_guilds.append(guild_id)
        config.primary_guild = guild_id
        created.append(guild_id)
        return cfg

    yield _make

    # Cleanup
    for gid in created:
        config.guilds.pop(gid, None)
        config.authorized_guilds.discard(gid)
        if gid in config.valid_guilds:
            config.valid_guilds.remove(gid)
    config.primary_guild = None


@pytest.fixture
def guild(make_guild):
    """Default guild config: epoch 2024-01-01, year 1, 14-day years, rollover 17:00 UTC."""
    return make_guild()


@pytest.fixture
def mock_ctx_factory():
    """Factory fixture: creates a mock ApplicationContext for command testing."""

    def _make_ctx(
        guild_id=TEST_GUILD,
        user_id=TEST_USER,
        channel_id=TEST_CHANNEL,
        is_owner=False,
        channel_name='test-channel',
        channel_type=None,
    ):
        """Create a mock ApplicationContext with configurable properties.

        Args:
            guild_id: Guild ID for ctx.guild.id
            user_id: User ID for ctx.user.id / ctx.author.id
            channel_id: Channel ID for ctx.channel.id
            is_owner: Whether user should be treated as bot owner
            channel_name: Name of the channel
            channel_type: discord.ChannelType or None for text channel

        Returns:
            Mock ApplicationContext with .respond() call tracking
        """
        from discord.enums import ChannelType

        # Create mock objects
        ctx = MagicMock()
        ctx.respond = AsyncMock()
        ctx.edit = AsyncMock()
        ctx.defer = AsyncMock()

        # Guild
        ctx.guild = MagicMock()
        ctx.guild.id = guild_id
        ctx.guild.name = 'Test Guild'
        ctx.guild.get_channel = MagicMock()
        ctx.guild.get_channel_or_thread = MagicMock()

        # User/Author
        ctx.user = MagicMock()
        ctx.user.id = user_id
        ctx.user.global_name = 'TestUser'
        ctx.user.mention = f'<@{user_id}>'
        ctx.author = ctx.user  # alias

        # Channel
        ctx.channel = MagicMock()
        ctx.channel.id = channel_id
        ctx.channel.name = channel_name
        ctx.channel.type = channel_type if channel_type is not None else ChannelType.text

        # Bot
        ctx.bot = MagicMock()
        ctx.bot.get_guild = MagicMock(return_value=ctx.guild)
        ctx.bot.user = MagicMock()
        ctx.bot.user.id = 1111111111

        # Command
        ctx.command = MagicMock()
        ctx.command.name = 'test_command'

        # Track if owner
        ctx._is_owner = is_owner

        # Response tracking
        ctx._responses = []

        async def track_respond(*args, **kwargs):
            ctx._responses.append({'args': args, 'kwargs': kwargs})

        ctx.respond = AsyncMock(side_effect=track_respond)

        return ctx

    return _make_ctx


@pytest.fixture
def mock_ctx(mock_ctx_factory):
    """Default mock ApplicationContext."""
    return mock_ctx_factory()


# --- Database and Repository Mocking Fixtures ---


@pytest.fixture
def mock_db():
    """Mock database instance for testing.

    Use this when you need to mock the database connection itself.
    Provides clean context management without nested `with` statements.

    Example:
        def test_something(mock_db):
            with patch('attubot.db.get_db', return_value=mock_db):
                # Your test code
                pass
    """
    return MagicMock()


@pytest.fixture
def mock_db_and_repos():
    """Mock database and reset repository instances.

    This fixture mocks the database and resets module-level repository instances,
    using a flat context manager pattern instead of nested `with` statements.

    Example:
        def test_something(mock_db_and_repos):
            # Database is mocked and repos are reset
            pass
    """
    mock_database = MagicMock()

    with patch('attubot.db.get_db', return_value=mock_database), patch('attubot.client.years._year_repo', None), patch('attubot.client.markers._marker_repo', None):
        yield mock_database


@pytest.fixture
def mock_year_repo():
    """Mock year repository for isolated testing.

    This fixture mocks the _get_repo() function in years.py, which is the
    preferred approach as it mocks the interface rather than internal state.

    Example:
        @pytest.mark.asyncio
        async def test_year_get(mock_year_repo):
            mock_year_repo.get = AsyncMock(return_value=some_doc)
            result = await Year.get(TEST_GUILD, 1)
            assert result is not None
    """
    repo = AsyncMock()
    with patch('attubot.client.years._get_repo', return_value=repo):
        yield repo


@pytest.fixture
def mock_marker_repo():
    """Mock marker repository for isolated testing.

    This fixture mocks the _get_repo() function in markers.py.

    Example:
        @pytest.mark.asyncio
        async def test_marker_get(mock_marker_repo):
            mock_marker_repo.get = AsyncMock(return_value=some_doc)
            result = await YearMarker.get(channel_id, 1)
            assert result is not None
    """
    repo = AsyncMock()
    with patch('attubot.client.markers._get_repo', return_value=repo):
        yield repo


@pytest.fixture
def mock_all_repos():
    """Mock both year and marker repositories for integrated testing.

    Returns a dict with 'year' and 'marker' keys containing the mocked repos.
    This avoids nested context managers when testing code that uses both repos.

    Example:
        @pytest.mark.asyncio
        async def test_rollover(mock_all_repos):
            mock_all_repos['year'].get_latest = AsyncMock(return_value=year_doc)
            mock_all_repos['marker'].get = AsyncMock(return_value=marker_doc)
            # Test code using both repos
    """
    year_repo = AsyncMock()
    marker_repo = AsyncMock()

    with patch('attubot.client.years._get_repo', return_value=year_repo), patch('attubot.client.markers._get_repo', return_value=marker_repo):
        yield {'year': year_repo, 'marker': marker_repo}


# --- Year Model Fixtures ---


@pytest.fixture
def make_year_doc():
    """Factory fixture: creates a YearDocument for testing.

    Example:
        def test_something(make_year_doc):
            doc = make_year_doc(year=5, start_time=1700000000)
            assert doc.year == 5
    """

    def _make(guild=TEST_GUILD, year=1, start_time=1704067200, end_time=1705276800, duration=14, notes=''):
        from attubot.database.models import YearDocument

        return YearDocument(
            guild=guild,
            year=year,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            notes=notes,
        )

    return _make


# --- Component Test Infrastructure (real MongoDB, isolated per-test collections) ---


def _read_db_config() -> tuple[str, str]:
    """read database url and name from the toml config, falling back to localhost defaults."""
    config_path = Path(os.environ.get('ATTU_CONFIG_FILE', './assets/attu-bot.toml'))
    if config_path.exists():
        with config_path.open() as f:
            raw = tomlkit.load(f)
        return str(raw['database']['url']), str(raw['database']['name'])  # pyright: ignore[reportIndexIssue]
    return 'mongodb://mongo:27017', 'doombot'


class _PrefixedDB:
    """wraps a pymongo AsyncDatabase, prepending a per-test prefix to every collection name."""

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


@pytest_asyncio.fixture
async def component_db():
    """connect to the live mongodb and wrap it with a per-test collection prefix.

    each test gets uniquely-named collections that are dropped at teardown.
    mark tests that use this with pytest.mark.component.
    """
    from pymongo import AsyncMongoClient

    url, db_name = _read_db_config()
    client = AsyncMongoClient(url, serverSelectionTimeoutMS=5000)
    prefix = f'test_{uuid.uuid4().hex[:10]}'
    wrapped = _PrefixedDB(client[db_name], prefix)
    yield wrapped
    await wrapped.cleanup()
    await client.close()


@pytest.fixture
def make_year():
    """Factory fixture: creates a Year instance for testing.

    Example:
        def test_something(make_year):
            year = make_year(year=5, start_time=1700000000)
            assert year.year == 5
    """

    def _make(guild=TEST_GUILD, year=1, start_time=1704067200, end_time=1705276800, duration=14, notes=''):
        from attubot.client.years import Year

        return Year(
            guild=guild,
            year=year,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            notes=notes,
        )

    return _make
