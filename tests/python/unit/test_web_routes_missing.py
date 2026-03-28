"""
AttuBot - Web Routes API Tests (Missing Cases)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests for the web API routes in attubot/web/routes.py covering cases not present in test_web_routes.py
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from attubot.config import BotTheme, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers


test_guild = 1234567890
test_guild_2 = 9876543210


@pytest_asyncio.fixture(scope='function')
async def web_app():
    """Create a test Quart web app with mocked config"""
    from attubot.web import app as web_app_module
    from attubot.web.app import create_app

    # Create test guild configs
    guild1 = GuildConfig(
        id=test_guild,
        channels=GuildChannels(
            activity=111111,
            announcements=222222,
            year_vc=333333,
            year_links=444444,
            meta_chat=555555,
            lore_channels=[666666, 777777],
            canon_channels=[888888],
        ),
        epoch=GuildEpoch(
            time=1704067200,
            year=5,
            length=14,
            paused=False,
            rollover_minutes=1020,
        ),
        roles=GuildRoles(announcements=999999),
        users=GuildUsers(markers=[111, 222, 333]),
    )

    guild2 = GuildConfig(
        id=test_guild_2,
        channels=GuildChannels(),
        epoch=GuildEpoch(),
        roles=GuildRoles(),
        users=GuildUsers(),
    )

    # Mock theme
    theme = BotTheme(
        rotation=180.0,
        max_rate=0.75,
        bot_color='#ff0000',
        guild_color='#00ff00',
    )

    # Set up test configuration directly on web_app_module.config
    web_app_module.config.authorized_guilds = {test_guild, test_guild_2}
    web_app_module.config.valid_guilds = [test_guild]
    web_app_module.config.primary_guild = test_guild
    web_app_module.config.guilds = {
        test_guild: guild1,
        test_guild_2: guild2,
    }
    web_app_module.config.theme = theme
    web_app_module.config.load_guild = AsyncMock(return_value=True)
    web_app_module.config.load_globals = AsyncMock()
    web_app_module.config.config_repo = MagicMock()
    web_app_module.config.config_repo.update_system_field = AsyncMock()
    web_app_module.config.error_log = (test_guild, 123456)
    web_app_module.config.error_hook = 'https://discord.com/api/webhooks/123/abc'
    web_app_module.config.config_version = '2.2.0'

    # Provide TOML-sourced config values and mark init as done so create_app()
    # skips on_init() (which would overwrite the manually-set test config).
    from attubot.config import PathsConfig, WebConfig

    web_app_module.config.web = WebConfig(secret_key='test-secret-key')
    web_app_module.config.paths = PathsConfig(assets='./assets')
    web_app_module.config._get_event('init').set()

    # Patch save methods on Pydantic models (can't assign directly due to Pydantic validation)
    with patch.object(GuildConfig, 'save', new=AsyncMock()), patch.object(BotTheme, 'save', new=AsyncMock()):
        app = create_app()
        app.config['TESTING'] = True
        yield app


@pytest_asyncio.fixture(scope='function')
async def client(web_app):
    """Create test client for the web app"""
    return web_app.test_client()


# ========== New Test Cases ==========


class TestMissingGuildRoutes:
    @pytest.mark.asyncio
    async def test_get_guild_not_found(self, client):
        """Test GET /api/guilds/<id> when guild is authorized but not in config"""
        from attubot.web.app import config

        # Simulate guild being in authorized_guilds but missing from config.guilds
        # (This shouldn't happen in normal operation but good to test handling)
        with patch.dict(config.guilds, {}, clear=False):
            del config.guilds[test_guild]
            response = await client.get(f'/api/guilds/{test_guild}')
            assert response.status_code == 404
            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_save_guild_not_found(self, client):
        """Test POST /api/guilds/<id> when guild is authorized but not in config"""
        from attubot.web.app import config

        with patch.dict(config.guilds, {}, clear=False):
            del config.guilds[test_guild]
            response = await client.post(f'/api/guilds/{test_guild}', json={})
            assert response.status_code == 404
            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_guild_config_page_not_found(self, client):
        """Test guild config page for authorized but missing guild"""
        from attubot.web.app import config

        with patch.dict(config.guilds, {}, clear=False):
            del config.guilds[test_guild]
            response = await client.get(f'/guild/{test_guild}')
            assert response.status_code == 404
            html = await response.get_data(as_text=True)
            assert 'Not Found' in html


class TestMissingThemeRoutes:
    @pytest.mark.asyncio
    async def test_get_theme_not_found(self, client):
        """Test GET /api/theme when theme is missing from config"""
        from attubot.web.app import config

        with patch.object(config, 'theme', None):
            response = await client.get('/api/theme')
            assert response.status_code == 404
            data = await response.get_json()
            assert 'error' in data


class TestMissingSystemRoutes:
    @pytest.mark.asyncio
    async def test_save_system_validation_details(self, client):
        """Test POST /api/system validation details structure"""
        # Sending invalid data to check error details format
        payload = {
            'primary_guild': -1,  # Invalid
        }
        response = await client.post('/api/system', json=payload)
        assert response.status_code == 400
        data = await response.get_json()
        assert 'details' in data
        assert isinstance(data['details'], list)
        assert 'loc' in data['details'][0]
        assert 'msg' in data['details'][0]
        assert 'type' in data['details'][0]


class TestMissingAuditRoutes:
    @pytest.mark.asyncio
    async def test_audit_logs_error_handling(self, client):
        """Test GET /api/audit error handling"""
        from attubot.web import app as web_app_module

        # Mock audit logger to raise exception
        mock_audit_logger = MagicMock()
        mock_audit_logger.get_logs = AsyncMock(side_effect=Exception('DB Error'))
        web_app_module.audit_logger = mock_audit_logger

        response = await client.get('/api/audit')
        assert response.status_code == 500
        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_audit_logs_timestamp_formatting(self, client):
        """Test timestamp formatting in audit logs"""
        from attubot.web import app as web_app_module

        timestamp = 1704067200  # 2024-01-01 00:00:00 UTC

        mock_audit_logger = MagicMock()
        mock_audit_logger.get_logs = AsyncMock(
            return_value=[
                {
                    'timestamp': timestamp,
                    '_id': 'some-id',
                    'config_type': 'test',
                    'action': 'test',
                    'success': True,
                }
            ]
        )
        web_app_module.audit_logger = mock_audit_logger

        response = await client.get('/api/audit')
        assert response.status_code == 200
        data = await response.get_json()
        assert len(data['logs']) == 1
        assert data['logs'][0]['timestamp_formatted'] == '2024-01-01 00:00:00'
        assert data['logs'][0]['_id'] == 'some-id'


class TestMissingAuthorization:
    @pytest.mark.asyncio
    async def test_validate_guild_unauthorized(self, client):
        """Test POST /api/guilds/<id>/validate for unauthorized guild"""
        response = await client.post('/api/guilds/999999/validate', json={})
        assert response.status_code == 403
        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_reset_guild_unauthorized(self, client):
        """Test POST /api/guilds/<id>/reset for unauthorized guild"""
        response = await client.post('/api/guilds/999999/reset')
        assert response.status_code == 403
        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_refresh_cache_unauthorized(self, client):
        """Test POST /api/guilds/<id>/refresh for unauthorized guild"""
        response = await client.post('/api/guilds/999999/refresh')
        assert response.status_code == 403
        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_get_channels_unauthorized(self, client):
        """Test GET /api/guilds/<id>/channels for unauthorized guild"""
        response = await client.get('/api/guilds/999999/channels')
        assert response.status_code == 403
        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_get_roles_unauthorized(self, client):
        """Test GET /api/guilds/<id>/roles for unauthorized guild"""
        response = await client.get('/api/guilds/999999/roles')
        assert response.status_code == 403
        data = await response.get_json()
        assert 'error' in data
