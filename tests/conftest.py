"""
AttuBot - Shared Test Fixtures
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests run with TZ=UTC so that datetime.fromtimestamp() and _config.timezone are consistent.
"""

import os
import time as _time

# Set timezone before any attubot imports (NovaConfig reads TZ in __init__)
os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot import config
from attubot.config import GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers

TEST_GUILD = 1234567890
TEST_USER = 9876543210
TEST_CHANNEL = 5555555555


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

    with patch('attubot.db.get_db', return_value=mock_database), \
         patch('attubot.years._year_repo', None), \
         patch('attubot.markers._marker_repo', None):
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
    with patch('attubot.years._get_repo', return_value=repo):
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
    with patch('attubot.markers._get_repo', return_value=repo):
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

    with patch('attubot.years._get_repo', return_value=year_repo), \
         patch('attubot.markers._get_repo', return_value=marker_repo):
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
    def _make(guild=TEST_GUILD, year=1, start_time=1704067200,
              end_time=1705276800, duration=14,
              formatted='# === Year 1 PC ===', notes=''):
        from attubot.database.models import YearDocument
        return YearDocument(
            guild=guild, year=year, start_time=start_time,
            end_time=end_time, duration=duration,
            formatted=formatted, notes=notes,
        )
    return _make


@pytest.fixture
def make_year():
    """Factory fixture: creates a Year instance for testing.

    Example:
        def test_something(make_year):
            year = make_year(year=5, start_time=1700000000)
            assert year.year == 5
    """
    def _make(guild=TEST_GUILD, year=1, start_time=1704067200,
              end_time=1705276800, duration=14,
              formatted='# === Year 1 PC ===', notes=''):
        from attubot.years import Year
        return Year(
            guild=guild, year=year, start_time=start_time,
            end_time=end_time, duration=duration,
            formatted=formatted, notes=notes,
        )
    return _make
