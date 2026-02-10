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

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

from attubot import config  # noqa: E402
from attubot.config import GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers  # noqa: E402

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
        config.primary_guild = guild_id
        created.append(guild_id)
        return cfg

    yield _make

    # Cleanup
    for gid in created:
        config.guilds.pop(gid, None)
        config.authorized_guilds.discard(gid)
    config.primary_guild = None


@pytest.fixture
def guild(make_guild):
    """Default guild config: epoch 2024-01-01, year 1, 14-day years, rollover 17:00 UTC."""
    return make_guild()


@pytest.fixture
def mock_ctx_factory():
    """Factory fixture: creates a mock ApplicationContext for command testing."""

    def _make_ctx(  # noqa: PLR0913
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
