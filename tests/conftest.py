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

import pytest  # noqa: E402

from attubot import config  # noqa: E402
from attubot.config import GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers  # noqa: E402

TEST_GUILD = 1234567890


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
