"""
AttuBot - Web Routes API Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests for the web API routes in attubot/web/routes.py
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from attubot.config import BotTheme, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers
from attubot.database.models import ChatChannelConfig, ChatConfigDocument


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

    # chat runtime config
    web_app_module.config.chat_runtime = ChatConfigDocument(
        discord_lookback_hours=6,
        discord_window_minutes=30,
        noise_filter_min_tokens=20,
        ingest_discord=True,
        ingest_wiki=True,
        ingest_documents=True,
        wiki_namespaces=['0'],
        retrieval_top_k_wiki=5,
        retrieval_top_k_discord=5,
        retrieval_top_k_documents=3,
        retrieval_top_k_images=2,
        chat_channels={'123456789': ChatChannelConfig(name='lore-news', channel_type='roleplay')},
        user_nations={'111111111': 'Faltir'},
    )
    web_app_module.config.chat_config_repo = MagicMock()
    web_app_module.config.chat_config_repo.save = AsyncMock()
    web_app_module.config.load_chat_runtime = AsyncMock(return_value=True)

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


# ========== Health Check Tests ==========


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test /health endpoint returns ok status"""
        response = await client.get('/health')
        assert response.status_code == 200

        data = await response.get_json()
        assert data['status'] == 'ok'
        assert data['service'] == 'attu-bot-web'
        assert 'config_loaded' in data


# ========== Page Route Tests ==========


class TestPageRoutes:
    @pytest.mark.asyncio
    async def test_index_page(self, client):
        """Test index page renders guild list"""
        response = await client.get('/')
        assert response.status_code == 200

        html = await response.get_data(as_text=True)
        assert 'Dashboard' in html
        assert str(test_guild) in html

    @pytest.mark.asyncio
    async def test_guild_config_page_authorized(self, client):
        """Test guild config page for authorized guild"""
        response = await client.get(f'/guild/{test_guild}')
        assert response.status_code == 200

        html = await response.get_data(as_text=True)
        assert 'Guild Configuration' in html

    @pytest.mark.asyncio
    async def test_guild_config_page_unauthorized(self, client):
        """Test guild config page for unauthorized guild"""
        response = await client.get('/guild/999999')
        assert response.status_code == 403

        html = await response.get_data(as_text=True)
        assert 'Unauthorized' in html or 'not authorized' in html

    @pytest.mark.asyncio
    async def test_theme_config_page(self, client):
        """Test theme config page renders"""
        response = await client.get('/theme')
        assert response.status_code == 200

        html = await response.get_data(as_text=True)
        assert 'Theme Configuration' in html

    @pytest.mark.asyncio
    async def test_system_config_page(self, client):
        """Test system config page renders"""
        response = await client.get('/system')
        assert response.status_code == 200

        html = await response.get_data(as_text=True)
        assert 'System Configuration' in html


# ========== Guild API Tests ==========


class TestGuildAPI:
    @pytest.mark.asyncio
    async def test_list_guilds(self, client):
        """Test GET /api/guilds lists all authorized guilds"""
        response = await client.get('/api/guilds')
        assert response.status_code == 200

        data = await response.get_json()
        assert 'guilds' in data
        assert len(data['guilds']) == 2

        guild_ids = [g['id'] for g in data['guilds']]
        assert str(test_guild) in guild_ids  # Guild IDs are strings to preserve precision
        assert str(test_guild_2) in guild_ids

    @pytest.mark.asyncio
    async def test_get_guild_config(self, client):
        """Test GET /api/guilds/<id> returns guild configuration"""
        response = await client.get(f'/api/guilds/{test_guild}')
        assert response.status_code == 200

        data = await response.get_json()
        assert data['guild_id'] == str(test_guild)  # Guild ID is string to preserve precision
        assert data['channels']['activity'] == '111111'  # All snowflake IDs as strings
        assert data['channels']['announcements'] == '222222'
        assert data['channels']['lore_channels'] == ['666666', '777777']
        assert data['epoch']['year'] == 5
        assert data['epoch']['length'] == 14
        assert data['epoch']['rollover_time'] == '17:00'
        assert data['roles']['announcements'] == '999999'
        assert data['users']['markers'] == ['111', '222', '333']

    @pytest.mark.asyncio
    async def test_get_guild_unauthorized(self, client):
        """Test GET /api/guilds/<id> for unauthorized guild"""
        response = await client.get('/api/guilds/999999')
        assert response.status_code == 403

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_save_guild_config_valid(self, client):
        """Test POST /api/guilds/<id> saves valid configuration"""
        from attubot.web.app import config

        payload = {
            'channels': {
                'activity': 123456,
                'announcements': 789012,
                'lore_channels': [111, 222],
            },
            'epoch': {
                'time': 1704067200,
                'year': 10,
                'length': 7,
                'paused': True,
                'rollover_minutes': 720,
            },
            'roles': {
                'announcements': 555555,
            },
            'users': {
                'markers': [444, 555],
            },
        }

        # Reset the mock to clear any previous calls
        config.guilds[test_guild].save.reset_mock()

        response = await client.post(
            f'/api/guilds/{test_guild}',
            json=payload,
        )
        assert response.status_code == 200

        data = await response.get_json()
        assert data['success'] is True
        assert 'message' in data

        # Verify guild.save() was called
        config.guilds[test_guild].save.assert_called_once()

        # Verify configuration was updated
        guild = config.guilds[test_guild]
        assert guild.channels.activity == 123456
        assert guild.epoch.year == 10
        assert guild.roles.announcements == 555555

    @pytest.mark.asyncio
    async def test_save_guild_config_flat_format(self, client):
        """Test POST /api/guilds/<id> with flat form data"""
        from attubot.web.app import config

        payload = {
            'channels.activity': 654321,
            'epoch.year': 15,
            'roles.announcements': 777777,
        }

        response = await client.post(
            f'/api/guilds/{test_guild}',
            json=payload,
        )
        assert response.status_code == 200

        # Verify configuration was updated
        guild = config.guilds[test_guild]
        assert guild.channels.activity == 654321
        assert guild.epoch.year == 15
        assert guild.roles.announcements == 777777

    @pytest.mark.asyncio
    async def test_save_guild_config_invalid(self, client):
        """Test POST /api/guilds/<id> with invalid data"""
        payload = {
            'epoch': {
                'year': -1,  # Invalid: must be >= 1
                'length': 14,  # Need to provide other required fields
                'time': 0,
                'paused': False,
                'rollover_minutes': 1020,
            },
        }

        response = await client.post(
            f'/api/guilds/{test_guild}',
            json=payload,
        )
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data
        assert 'details' in data

    @pytest.mark.asyncio
    async def test_save_guild_no_data(self, client):
        """Test POST /api/guilds/<id> with no data"""
        response = await client.post(f'/api/guilds/{test_guild}')
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_validate_guild_config_valid(self, client):
        """Test POST /api/guilds/<id>/validate with valid data"""
        payload = {
            'channels': {'activity': 123456},
            'epoch': {'year': 5, 'rollover_minutes': '17:00'},
        }

        response = await client.post(
            f'/api/guilds/{test_guild}/validate',
            json=payload,
        )
        assert response.status_code == 200

        data = await response.get_json()
        assert data['valid'] is True
        assert 'data' in data

    @pytest.mark.asyncio
    async def test_validate_guild_config_invalid(self, client):
        """Test POST /api/guilds/<id>/validate with invalid data"""
        payload = {
            'epoch': {
                'year': 1,
                'length': 500,  # Invalid: max 365
                'time': 0,
                'paused': False,
                'rollover_minutes': 1020,
            },
        }

        response = await client.post(
            f'/api/guilds/{test_guild}/validate',
            json=payload,
        )
        assert response.status_code == 400

        data = await response.get_json()
        assert data['valid'] is False
        assert 'details' in data

    @pytest.mark.asyncio
    async def test_reset_guild_config(self, client):
        """Test POST /api/guilds/<id>/reset reloads from database"""
        from attubot.web.app import config

        response = await client.post(f'/api/guilds/{test_guild}/reset')
        assert response.status_code == 200

        data = await response.get_json()
        assert data['success'] is True

        # Verify load_guild was called
        config.load_guild.assert_called_once_with(test_guild)

    @pytest.mark.asyncio
    async def test_reset_guild_config_failure(self, client):
        """Test POST /api/guilds/<id>/reset handles failure"""
        from attubot.web.app import config

        config.load_guild = AsyncMock(return_value=False)

        response = await client.post(f'/api/guilds/{test_guild}/reset')
        assert response.status_code == 500

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_get_channels(self, client):
        """Test GET /api/guilds/<id>/channels returns channel list"""
        mock_channels = [
            {'id': '111', 'name': 'text-channel', 'type': 'text', 'position': 1},
            {'id': '222', 'name': 'voice-channel', 'type': 'voice', 'position': 2},
        ]

        with patch('attubot.web.routes.get_guild_channels', new=AsyncMock(return_value=mock_channels)):
            response = await client.get(f'/api/guilds/{test_guild}/channels')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'channels' in data
            assert len(data['channels']) == 2
            assert data['channels'][0]['name'] == 'text-channel'

    @pytest.mark.asyncio
    async def test_get_roles(self, client):
        """Test GET /api/guilds/<id>/roles returns role list"""
        mock_roles = [
            {'id': '999', 'name': 'Admin', 'color': '0xff0000', 'position': 1},
        ]

        with patch('attubot.web.routes.get_guild_roles', new=AsyncMock(return_value=mock_roles)):
            response = await client.get(f'/api/guilds/{test_guild}/roles')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'roles' in data
            assert len(data['roles']) == 1
            assert data['roles'][0]['name'] == 'Admin'

    @pytest.mark.asyncio
    async def test_refresh_discord_cache(self, client):
        """Test POST /api/guilds/<id>/refresh clears cache"""
        with patch('attubot.web.routes.invalidate_guild_cache') as mock_invalidate:
            response = await client.post(f'/api/guilds/{test_guild}/refresh')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['success'] is True
            mock_invalidate.assert_called_once_with(test_guild)


# ========== Theme API Tests ==========


class TestThemeAPI:
    @pytest.mark.asyncio
    async def test_get_theme(self, client):
        """Test GET /api/theme returns theme configuration"""
        response = await client.get('/api/theme')
        assert response.status_code == 200

        data = await response.get_json()
        assert data['rotation'] == 180.0
        assert data['max_rate'] == 0.75
        assert data['bot_color'] == '#ff0000'
        assert data['guild_color'] == '#00ff00'

    @pytest.mark.asyncio
    async def test_save_theme_valid(self, client):
        """Test POST /api/theme saves valid theme"""
        from attubot.web.app import config

        payload = {
            'rotation': 90.0,
            'max_rate': 0.5,
            'bot_color': '#0000ff',
            'guild_color': '#ffff00',
        }

        # Reset the mock to clear any previous calls
        config.theme.save.reset_mock()

        response = await client.post('/api/theme', json=payload)
        assert response.status_code == 200

        data = await response.get_json()
        assert data['success'] is True

        # Verify theme.save() was called
        config.theme.save.assert_called_once()

        # Verify theme was updated
        assert config.theme.rotation == 90.0
        assert config.theme.max_rate == 0.5
        assert config.theme.bot_color == '#0000ff'
        assert config.theme.guild_color == '#ffff00'

    @pytest.mark.asyncio
    async def test_save_theme_invalid_color(self, client):
        """Test POST /api/theme with invalid color format"""
        payload = {
            'bot_color': 'not-a-color',
        }

        response = await client.post('/api/theme', json=payload)
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_save_theme_invalid_max_rate(self, client):
        """Test POST /api/theme with invalid max_rate"""
        payload = {
            'max_rate': 360.1,  # Invalid: max 360.0
        }

        response = await client.post('/api/theme', json=payload)
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data


# ========== System API Tests ==========


class TestSystemAPI:
    @pytest.mark.asyncio
    async def test_get_system_config(self, client):
        """Test GET /api/system returns system configuration"""
        response = await client.get('/api/system')
        assert response.status_code == 200

        data = await response.get_json()
        assert data['version'] == '2.2.0'
        assert data['primary_guild'] == str(test_guild)
        assert data['error_log_guild'] == str(test_guild)
        assert data['error_log_channel'] == str(123456)
        assert data['error_hook'] == 'https://discord.com/api/webhooks/123/abc'

    @pytest.mark.asyncio
    async def test_save_system_config_valid(self, client):
        """Test POST /api/system saves valid system config"""
        from attubot.web.app import config

        payload = {
            'primary_guild': test_guild_2,
            'error_log_guild': test_guild,
            'error_log_channel': 999999,
            'error_hook': 'https://discord.com/api/webhooks/456/xyz',
        }

        response = await client.post('/api/system', json=payload)
        assert response.status_code == 200

        data = await response.get_json()
        assert data['success'] is True

        # Verify config_repo methods were called
        assert config.config_repo.update_system_field.call_count == 3
        config.load_globals.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_system_config_invalid_webhook(self, client):
        """Test POST /api/system with invalid webhook URL"""
        payload = {
            'primary_guild': test_guild,
            'error_hook': 'http://example.com',  # Invalid: not Discord webhook
        }

        response = await client.post('/api/system', json=payload)
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_save_system_config_negative_guild(self, client):
        """Test POST /api/system with negative guild ID"""
        payload = {
            'primary_guild': -1,  # Invalid
        }

        response = await client.post('/api/system', json=payload)
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data


# ========== Chat Config API Tests ==========


class TestChatAPI:
    @pytest.mark.asyncio
    async def test_chat_config_page(self, client):
        """Test /chat page renders"""
        response = await client.get('/chat')
        assert response.status_code == 200

        html = await response.get_data(as_text=True)
        assert 'Chat Configuration' in html

    @pytest.mark.asyncio
    async def test_get_chat_config(self, client):
        """Test GET /api/chat returns chat runtime config"""
        response = await client.get('/api/chat')
        assert response.status_code == 200

        data = await response.get_json()
        assert data['discord_lookback_hours'] == 6
        assert data['discord_window_minutes'] == 30
        assert data['ingest_wiki'] is True
        assert data['wiki_namespaces'] == ['0']
        assert '123456789' in data['chat_channels']
        assert data['chat_channels']['123456789']['channel_type'] == 'roleplay'
        assert data['user_nations']['111111111'] == 'Faltir'
        assert data['character_log_channel_id'] is None

    @pytest.mark.asyncio
    async def test_save_chat_config_valid(self, client):
        """Test POST /api/chat saves valid config"""
        from attubot.web import app as web_app_module

        payload = {
            'discord_lookback_hours': 12,
            'discord_window_minutes': 45,
            'noise_filter_min_tokens': 15,
            'ingest_wiki': True,
            'ingest_discord': False,
            'ingest_documents': True,
            'wiki_namespaces': ['0'],
            'retrieval_top_k_wiki': 8,
            'retrieval_top_k_discord': 3,
            'retrieval_top_k_documents': 2,
            'retrieval_top_k_images': 1,
            'chat_channels': {},
            'user_nations': {},
        }

        web_app_module.config.chat_config_repo.save.reset_mock()
        web_app_module.config.load_chat_runtime.reset_mock()

        response = await client.post('/api/chat', json=payload)
        assert response.status_code == 200

        data = await response.get_json()
        assert data['success'] is True

        web_app_module.config.chat_config_repo.save.assert_called_once()
        web_app_module.config.load_chat_runtime.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_chat_config_invalid_top_k(self, client):
        """Test POST /api/chat rejects retrieval_top_k < 1"""
        response = await client.post('/api/chat', json={'retrieval_top_k_wiki': 0})
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_save_chat_config_invalid_channel_type(self, client):
        """Test POST /api/chat rejects unknown channel_type"""
        response = await client.post('/api/chat', json={
            'chat_channels': {'123': {'channel_type': 'invalid'}},
        })
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_save_chat_config_invalid_lookback(self, client):
        """Test POST /api/chat rejects discord_lookback_hours < 1"""
        response = await client.post('/api/chat', json={'discord_lookback_hours': 0})
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_save_chat_config_no_data(self, client):
        """Test POST /api/chat with empty body returns 400"""
        response = await client.post('/api/chat')
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_save_chat_config_database_error(self, client):
        """Test POST /api/chat handles database errors"""
        from attubot.web import app as web_app_module

        web_app_module.config.chat_config_repo.save.side_effect = Exception('db error')

        response = await client.post('/api/chat', json={'discord_lookback_hours': 6})
        assert response.status_code == 500

        data = await response.get_json()
        assert 'error' in data

        web_app_module.config.chat_config_repo.save.side_effect = None


# ========== Audit Log Tests ==========


class TestAuditLogAPI:
    @pytest.mark.asyncio
    async def test_audit_log_page(self, client):
        """Test GET /audit renders audit log page"""
        response = await client.get('/audit')
        assert response.status_code == 200

        html = await response.get_data(as_text=True)
        assert 'Audit Log' in html
        assert 'filterConfigType' in html  # Check for filter elements

    @pytest.mark.asyncio
    async def test_get_audit_logs_empty(self, client):
        """Test GET /api/audit returns empty list when no logs exist"""
        from attubot.web import app as web_app_module

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        mock_audit_logger.get_logs = AsyncMock(return_value=[])
        web_app_module.audit_logger = mock_audit_logger

        response = await client.get('/api/audit')
        assert response.status_code == 200

        data = await response.get_json()
        assert 'logs' in data
        assert data['logs'] == []
        assert data['count'] == 0

    @pytest.mark.asyncio
    async def test_get_audit_logs_with_data(self, client):
        """Test GET /api/audit returns audit logs"""
        import time

        from attubot.web import app as web_app_module

        # Mock audit_logger with sample data
        mock_audit_logger = MagicMock()
        sample_logs = [
            {
                'timestamp': int(time.time()),
                'ip_address': '127.0.0.1',
                'config_type': 'guild',
                'action': 'update',
                'guild_id': test_guild,
                'success': True,
                'changes': [
                    {'field': 'channels.activity', 'old_value': 111111, 'new_value': 222222},
                ],
            },
            {
                'timestamp': int(time.time()) - 100,
                'ip_address': '127.0.0.1',
                'config_type': 'theme',
                'action': 'update',
                'guild_id': None,
                'success': True,
                'changes': [
                    {'field': 'rotation', 'old_value': 0.0, 'new_value': 180.0},
                ],
            },
        ]
        mock_audit_logger.get_logs = AsyncMock(return_value=sample_logs)
        web_app_module.audit_logger = mock_audit_logger

        response = await client.get('/api/audit')
        assert response.status_code == 200

        data = await response.get_json()
        assert 'logs' in data
        assert len(data['logs']) == 2
        assert data['count'] == 2

        # Verify log structure
        log = data['logs'][0]
        assert log['config_type'] == 'guild'
        assert log['action'] == 'update'
        assert log['success'] is True
        assert 'timestamp_formatted' in log

    @pytest.mark.asyncio
    async def test_get_audit_logs_with_config_type_filter(self, client):
        """Test GET /api/audit with config_type filter"""
        import time

        from attubot.web import app as web_app_module

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        guild_logs = [
            {
                'timestamp': int(time.time()),
                'ip_address': '127.0.0.1',
                'config_type': 'guild',
                'action': 'update',
                'guild_id': test_guild,
                'success': True,
                'changes': [],
            },
        ]
        mock_audit_logger.get_logs = AsyncMock(return_value=guild_logs)
        web_app_module.audit_logger = mock_audit_logger

        response = await client.get('/api/audit?config_type=guild')
        assert response.status_code == 200

        data = await response.get_json()
        assert len(data['logs']) == 1
        assert data['logs'][0]['config_type'] == 'guild'

        # Verify get_logs was called with correct parameters
        mock_audit_logger.get_logs.assert_called_once()
        call_kwargs = mock_audit_logger.get_logs.call_args.kwargs
        assert call_kwargs['config_type'] == 'guild'

    @pytest.mark.asyncio
    async def test_get_audit_logs_with_guild_filter(self, client):
        """Test GET /api/audit with guild_id filter"""
        import time

        from attubot.web import app as web_app_module

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        guild_logs = [
            {
                'timestamp': int(time.time()),
                'ip_address': '127.0.0.1',
                'config_type': 'guild',
                'action': 'update',
                'guild_id': test_guild,
                'success': True,
                'changes': [],
            },
        ]
        mock_audit_logger.get_logs = AsyncMock(return_value=guild_logs)
        web_app_module.audit_logger = mock_audit_logger

        response = await client.get(f'/api/audit?guild_id={test_guild}')
        assert response.status_code == 200

        data = await response.get_json()
        assert len(data['logs']) == 1
        assert data['logs'][0]['guild_id'] == str(test_guild)  # Guild IDs are strings to preserve precision

        # Verify get_logs was called with correct parameters
        call_kwargs = mock_audit_logger.get_logs.call_args.kwargs
        assert call_kwargs['guild_id'] == test_guild

    @pytest.mark.asyncio
    async def test_get_audit_logs_with_pagination(self, client):
        """Test GET /api/audit with limit and skip parameters"""
        from attubot.web import app as web_app_module

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        mock_audit_logger.get_logs = AsyncMock(return_value=[])
        web_app_module.audit_logger = mock_audit_logger

        response = await client.get('/api/audit?limit=25&skip=50')
        assert response.status_code == 200

        # Verify get_logs was called with correct pagination parameters
        call_kwargs = mock_audit_logger.get_logs.call_args.kwargs
        assert call_kwargs['limit'] == 25
        assert call_kwargs['skip'] == 50

    @pytest.mark.asyncio
    async def test_get_audit_logs_no_logger(self, client):
        """Test GET /api/audit when audit_logger is not initialized"""
        from attubot.web import app as web_app_module

        # Set audit_logger to None
        web_app_module.audit_logger = None

        response = await client.get('/api/audit')
        assert response.status_code == 503

        data = await response.get_json()
        assert 'error' in data
        assert 'not available' in data['error'].lower()

    @pytest.mark.asyncio
    async def test_audit_logging_on_guild_save(self, client):
        """Test that saving guild config creates audit log entry"""
        from attubot.web import app as web_app_module

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        mock_audit_logger.log_change = AsyncMock()
        web_app_module.audit_logger = mock_audit_logger

        payload = {
            'channels': {
                'activity': 999999,
            },
            'epoch': {
                'year': 10,
            },
        }

        response = await client.post(f'/api/guilds/{test_guild}', json=payload)
        assert response.status_code == 200

        # Verify log_change was called
        mock_audit_logger.log_change.assert_called_once()
        call_kwargs = mock_audit_logger.log_change.call_args.kwargs

        assert call_kwargs['config_type'] == 'guild'
        assert call_kwargs['action'] == 'update'
        assert call_kwargs['guild_id'] == test_guild
        assert call_kwargs['success'] is True
        assert len(call_kwargs['changes']) > 0

    @pytest.mark.asyncio
    async def test_audit_logging_on_theme_save(self, client):
        """Test that saving theme config creates audit log entry"""
        from attubot.web import app as web_app_module

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        mock_audit_logger.log_change = AsyncMock()
        web_app_module.audit_logger = mock_audit_logger

        payload = {
            'rotation': 45.0,
            'bot_color': '#123456',
        }

        response = await client.post('/api/theme', json=payload)
        assert response.status_code == 200

        # Verify log_change was called
        mock_audit_logger.log_change.assert_called_once()
        call_kwargs = mock_audit_logger.log_change.call_args.kwargs

        assert call_kwargs['config_type'] == 'theme'
        assert call_kwargs['action'] == 'update'
        assert call_kwargs['success'] is True
        assert len(call_kwargs['changes']) > 0

    @pytest.mark.asyncio
    async def test_audit_logging_on_system_save(self, client):
        """Test that saving system config creates audit log entry"""
        from attubot.web import app as web_app_module
        from attubot.web.app import config

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        mock_audit_logger.log_change = AsyncMock()
        web_app_module.audit_logger = mock_audit_logger

        # Mock load_globals to update config values
        async def mock_load_globals():
            config.primary_guild = test_guild_2
            config.error_log = (test_guild, 888888)
            config.error_hook = 'https://discord.com/api/webhooks/123/abc'

        config.load_globals = AsyncMock(side_effect=mock_load_globals)

        payload = {
            'primary_guild': test_guild_2,
            'error_log_channel': 888888,
        }

        response = await client.post('/api/system', json=payload)
        assert response.status_code == 200

        # Verify log_change was called
        mock_audit_logger.log_change.assert_called_once()
        call_kwargs = mock_audit_logger.log_change.call_args.kwargs

        assert call_kwargs['config_type'] == 'system'
        assert call_kwargs['action'] == 'update'
        assert call_kwargs['success'] is True
        assert len(call_kwargs['changes']) > 0

    @pytest.mark.asyncio
    async def test_audit_logging_on_failed_save(self, client):
        """Test that failed save attempts are also logged"""
        from attubot.web import app as web_app_module
        from attubot.web.app import config

        # Mock audit_logger
        mock_audit_logger = MagicMock()
        mock_audit_logger.log_change = AsyncMock()
        web_app_module.audit_logger = mock_audit_logger

        # Configure the mock to raise an exception
        config.guilds[test_guild].save.side_effect = Exception('Database error')

        payload = {
            'channels': {'activity': 123456},
        }

        response = await client.post(f'/api/guilds/{test_guild}', json=payload)
        assert response.status_code == 500

        # Verify log_change was called with success=False
        mock_audit_logger.log_change.assert_called_once()
        call_kwargs = mock_audit_logger.log_change.call_args.kwargs

        assert call_kwargs['success'] is False
        assert call_kwargs['error_message'] is not None

        # Reset the mock for other tests
        config.guilds[test_guild].save.side_effect = None

    @pytest.mark.asyncio
    async def test_audit_logging_on_chat_save(self, client):
        """Test that saving chat config creates audit log entry"""
        from attubot.database.models import ChatConfigDocument
        from attubot.web import app as web_app_module
        from attubot.web.app import config as app_config

        mock_audit_logger = MagicMock()
        mock_audit_logger.log_change = AsyncMock()
        web_app_module.audit_logger = mock_audit_logger

        # make load_chat_runtime update chat_runtime so compare_configs finds changes
        async def mock_load_chat():
            app_config.chat_runtime = ChatConfigDocument(
                discord_lookback_hours=12,
                ingest_wiki=False,
            )

        web_app_module.config.load_chat_runtime = AsyncMock(side_effect=mock_load_chat)

        payload = {
            'discord_lookback_hours': 12,
            'ingest_wiki': False,
            'chat_channels': {},
            'user_nations': {},
        }
        response = await client.post('/api/chat', json=payload)
        assert response.status_code == 200

        mock_audit_logger.log_change.assert_called_once()
        call_kwargs = mock_audit_logger.log_change.call_args.kwargs
        assert call_kwargs['config_type'] == 'chat'
        assert call_kwargs['action'] == 'update'
        assert call_kwargs['success'] is True
        assert len(call_kwargs['changes']) > 0

        # reset
        web_app_module.config.load_chat_runtime = AsyncMock(return_value=True)


# ========== Error Handling Tests ==========


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_save_guild_database_error(self, client):
        """Test POST /api/guilds/<id> handles database errors"""
        from attubot.web.app import config

        payload = {
            'channels': {'activity': 123456},
        }

        # Configure the mock to raise an exception
        config.guilds[test_guild].save.side_effect = Exception('Database error')

        response = await client.post(f'/api/guilds/{test_guild}', json=payload)
        assert response.status_code == 500

        data = await response.get_json()
        assert 'error' in data

        # Reset the mock for other tests
        config.guilds[test_guild].save.side_effect = None

    @pytest.mark.asyncio
    async def test_save_theme_database_error(self, client):
        """Test POST /api/theme handles database errors"""
        from attubot.web.app import config

        payload = {
            'rotation': 45.0,
        }

        # Configure the mock to raise an exception
        config.theme.save.side_effect = Exception('Database error')

        response = await client.post('/api/theme', json=payload)
        assert response.status_code == 500

        data = await response.get_json()
        assert 'error' in data

        # Reset the mock for other tests
        config.theme.save.side_effect = None
