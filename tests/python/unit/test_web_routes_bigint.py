"""
AttuBot - Web Routes API Tests (BigInt Support)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests ensuring the backend correctly handles large integers (BigInts) as strings to support client-side precision.
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from attubot.config import BotTheme, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers


# Use a large integer that would lose precision in JS (MAX_SAFE_INTEGER is 9007199254740991)
# Discord IDs are uint64, which can go up to 18446744073709551615
large_id = 900719925474099200  # Larger than JS max safe integer
test_guild = 1234567890


@pytest_asyncio.fixture(scope='function')
async def web_app():
    """Create a test Quart web app with mocked config"""
    from attubot.web import app as web_app_module
    from attubot.web.app import create_app

    # Create test guild configs
    guild1 = GuildConfig(
        id=test_guild,
        channels=GuildChannels(
            activity=large_id,  # Use large ID here
            announcements=222222,
        ),
        epoch=GuildEpoch(),
        roles=GuildRoles(),
        users=GuildUsers(),
    )

    # Set up test configuration directly on web_app_module.config
    web_app_module.config.authorized_guilds = {test_guild}
    web_app_module.config.valid_guilds = [test_guild]
    web_app_module.config.primary_guild = test_guild
    web_app_module.config.guilds = {
        test_guild: guild1,
    }
    web_app_module.config.theme = BotTheme()
    web_app_module.config.load_guild = AsyncMock(return_value=True)
    web_app_module.config.load_globals = AsyncMock()
    web_app_module.config.config_repo = MagicMock()
    web_app_module.config.config_repo.update_system_field = AsyncMock()
    web_app_module.config.error_log = (test_guild, large_id)  # Use large ID here
    web_app_module.config.error_hook = ''
    web_app_module.config.config_version = '2.2.0'

    # Provide TOML-sourced config values and mark init as done so create_app()
    # skips on_init() (which would overwrite the manually-set test config).
    from attubot.config import PathsConfig, WebConfig

    web_app_module.config.web = WebConfig(secret_key='test-secret-key')
    web_app_module.config.paths = PathsConfig(assets='./assets')
    web_app_module.config._get_event('init').set()

    # Patch save methods on Pydantic models
    with patch.object(GuildConfig, 'save', new=AsyncMock()), patch.object(BotTheme, 'save', new=AsyncMock()):
        app = create_app()
        app.config['TESTING'] = True
        yield app


@pytest_asyncio.fixture(scope='function')
async def client(web_app):
    """Create test client for the web app"""
    return web_app.test_client()


class TestBigIntSupport:
    @pytest.mark.asyncio
    async def test_get_guild_returns_strings_for_ids(self, client):
        """Test that guild IDs in GET response are strings"""
        response = await client.get(f'/api/guilds/{test_guild}')
        assert response.status_code == 200

        data = await response.get_json()

        # Verify IDs are strings
        assert isinstance(data['guild_id'], str)
        assert data['guild_id'] == str(test_guild)

        assert isinstance(data['channels']['activity'], str)
        assert data['channels']['activity'] == str(large_id)

    @pytest.mark.asyncio
    async def test_save_guild_accepts_strings_and_ints(self, client):
        """Test that backend accepts both strings and ints for IDs"""
        from attubot.web.app import config

        # Case 1: Sending IDs as strings (like JS would for BigInts)
        payload_strings = {
            'channels': {
                'activity': str(large_id),
            },
        }

        response = await client.post(f'/api/guilds/{test_guild}', json=payload_strings)
        assert response.status_code == 200

        # Verify it was stored as int in backend
        assert config.guilds[test_guild].channels.activity == large_id

        # Case 2: Sending IDs as ints (standard JSON)
        payload_ints = {
            'channels': {
                'activity': large_id,
            },
        }

        response = await client.post(f'/api/guilds/{test_guild}', json=payload_ints)
        assert response.status_code == 200

        assert config.guilds[test_guild].channels.activity == large_id

    @pytest.mark.asyncio
    async def test_system_config_returns_ids_as_strings(self, client):
        """Test system config returns IDs as strings for BigInt support"""
        response = await client.get('/api/system')
        assert response.status_code == 200

        data = await response.get_json()

        # Verify IDs are strings
        assert isinstance(data['primary_guild'], str)
        assert data['primary_guild'] == str(test_guild)

        assert isinstance(data['error_log_guild'], str)
        assert data['error_log_guild'] == str(test_guild)

        assert isinstance(data['error_log_channel'], str)
        assert data['error_log_channel'] == str(large_id)

    @pytest.mark.asyncio
    async def test_list_guilds_returns_strings(self, client):
        """Test list guilds returns IDs as strings"""
        response = await client.get('/api/guilds')
        assert response.status_code == 200

        data = await response.get_json()
        for guild in data['guilds']:
            assert isinstance(guild['id'], str)
