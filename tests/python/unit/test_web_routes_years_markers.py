"""
AttuBot - Years, Markers, Time API Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests for the new years, markers, time, and admin stats API endpoints
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from attubot.config import BotTheme, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers


TEST_GUILD = 1234567890
TEST_GUILD_2 = 9876543210


@pytest_asyncio.fixture(scope='function')
async def web_app():
    """Create a test Quart web app with mocked config"""
    from attubot.web import app as web_app_module
    from attubot.web.app import create_app

    # Create test guild configs
    guild1 = GuildConfig(
        id=TEST_GUILD,
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
        id=TEST_GUILD_2,
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
    web_app_module.config.authorized_guilds = {TEST_GUILD, TEST_GUILD_2}
    web_app_module.config.valid_guilds = [TEST_GUILD]
    web_app_module.config.primary_guild = TEST_GUILD
    web_app_module.config.guilds = {
        TEST_GUILD: guild1,
        TEST_GUILD_2: guild2,
    }
    web_app_module.config.theme = theme
    web_app_module.config.load_guild = AsyncMock(return_value=True)
    web_app_module.config.load_globals = AsyncMock()
    web_app_module.config.config_repo = MagicMock()
    web_app_module.config.config_repo.update_system_field = AsyncMock()
    web_app_module.config.error_log = (TEST_GUILD, 123456)
    web_app_module.config.error_hook = 'https://discord.com/api/webhooks/123/abc'
    web_app_module.config.config_version = '2.2.0'

    # Set init time for uptime calculation
    web_app_module.config._init_time = _time.time() - 3600  # 1 hour ago

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


# ========== Years API Tests ==========


class TestYearsAPI:
    @pytest.mark.asyncio
    async def test_get_years_empty(self, client):
        """Test GET /api/guilds/<id>/years returns empty list when no years exist"""
        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.all_for_guild = AsyncMock(return_value=[])

            response = await client.get(f'/api/guilds/{TEST_GUILD}/years')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'years' in data
            assert data['years'] == []
            assert data['count'] == 0

    @pytest.mark.asyncio
    async def test_get_years_with_data(self, client):
        """Test GET /api/guilds/<id>/years returns year records"""
        # Create mock year instances
        mock_year1 = MagicMock()
        mock_year1.guild = TEST_GUILD
        mock_year1.year = 1
        mock_year1.start_time = 1704067200
        mock_year1.end_time = 1705708800
        mock_year1.duration = 19
        mock_year1.notes = 'First year'

        mock_year2 = MagicMock()
        mock_year2.guild = TEST_GUILD
        mock_year2.year = 2
        mock_year2.start_time = 1705708800
        mock_year2.end_time = 0
        mock_year2.duration = 0
        mock_year2.notes = ''

        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.all_for_guild = AsyncMock(return_value=[mock_year1, mock_year2])

            response = await client.get(f'/api/guilds/{TEST_GUILD}/years')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'years' in data
            assert len(data['years']) == 2
            assert data['count'] == 2
            assert data['years'][0]['year'] == 1
            assert data['years'][1]['year'] == 2

    @pytest.mark.asyncio
    async def test_get_year_specific(self, client):
        """Test GET /api/guilds/<id>/years/<year> returns specific year"""
        mock_year = MagicMock()
        mock_year.guild = TEST_GUILD
        mock_year.year = 5
        mock_year.start_time = 1704067200
        mock_year.end_time = 1705708800
        mock_year.duration = 19
        mock_year.notes = 'Fifth year'

        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.get = AsyncMock(return_value=mock_year)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/years/5')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['year'] == 5
            assert data['duration'] == 19

    @pytest.mark.asyncio
    async def test_get_year_not_found(self, client):
        """Test GET /api/guilds/<id>/years/<year> returns 404 for missing year"""
        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.get = AsyncMock(return_value=None)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/years/999')
            assert response.status_code == 404

            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_get_latest_year(self, client):
        """Test GET /api/guilds/<id>/years/latest returns most recent year"""
        mock_year = MagicMock()
        mock_year.guild = TEST_GUILD
        mock_year.year = 10
        mock_year.start_time = 1750000000
        mock_year.end_time = 0
        mock_year.duration = 0
        mock_year.notes = ''

        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.get_latest = AsyncMock(return_value=mock_year)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/years/latest')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['year'] == 10

    @pytest.mark.asyncio
    async def test_get_latest_year_not_found(self, client):
        """Test GET /api/guilds/<id>/years/latest returns 404 when no years"""
        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.get_latest = AsyncMock(return_value=None)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/years/latest')
            assert response.status_code == 404

            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_get_years_unauthorized(self, client):
        """Test GET /api/guilds/<id>/years returns 403 for unauthorized guild"""
        response = await client.get('/api/guilds/999999/years')
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_year_missing_start_time(self, client):
        """Test POST /api/guilds/<id>/years/<year> returns 400 when start_time missing"""
        response = await client.post(f'/api/guilds/{TEST_GUILD}/years/1', json={'notes': 'no start time'})
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_create_year_no_data(self, client):
        """Test POST /api/guilds/<id>/years/<year> returns 400 when no body"""
        response = await client.post(f'/api/guilds/{TEST_GUILD}/years/1')
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_create_year_db_error(self, client):
        """Test POST /api/guilds/<id>/years/<year> returns 500 on DB error"""
        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.get = AsyncMock(side_effect=Exception('DB connection lost'))

            response = await client.post(f'/api/guilds/{TEST_GUILD}/years/1', json={'start_time': 1704067200})
            assert response.status_code == 500

            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_create_year_unauthorized(self, client):
        """Test POST /api/guilds/<id>/years/<year> returns 403 for unauthorized guild"""
        response = await client.post('/api/guilds/999999/years/1', json={'start_time': 1704067200})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_year_not_found(self, client):
        """Test DELETE /api/guilds/<id>/years/<year> returns 404 when year missing"""
        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.get = AsyncMock(return_value=None)

            response = await client.delete(f'/api/guilds/{TEST_GUILD}/years/999')
            assert response.status_code == 404

            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_delete_year_db_error(self, client):
        """Test DELETE /api/guilds/<id>/years/<year> returns 500 on DB error"""
        with patch('attubot.years.Year') as mock_year_class:
            mock_year_class.get = AsyncMock(side_effect=Exception('DB connection lost'))

            response = await client.delete(f'/api/guilds/{TEST_GUILD}/years/5')
            assert response.status_code == 500

            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_delete_year_unauthorized(self, client):
        """Test DELETE /api/guilds/<id>/years/<year> returns 403 for unauthorized guild"""
        response = await client.delete('/api/guilds/999999/years/5')
        assert response.status_code == 403


# ========== Markers API Tests ==========


class TestMarkersAPI:
    @pytest.mark.asyncio
    async def test_get_markers_empty(self, client):
        """Test GET /api/guilds/<id>/markers returns empty list when no markers exist"""
        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.all_for_guild = AsyncMock(return_value=[])

            response = await client.get(f'/api/guilds/{TEST_GUILD}/markers')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'markers' in data
            assert data['markers'] == []
            assert data['count'] == 0

    @pytest.mark.asyncio
    async def test_get_markers_with_data(self, client):
        """Test GET /api/guilds/<id>/markers returns markers"""
        mock_marker1 = MagicMock()
        mock_marker1.channel = TEST_GUILD
        mock_marker1.message = 123456789012345678
        mock_marker1.year = 1
        mock_marker1.exact = True
        mock_marker1.wiki_page = False

        mock_marker2 = MagicMock()
        mock_marker2.channel = TEST_GUILD
        mock_marker2.message = 223456789012345678
        mock_marker2.year = 2
        mock_marker2.exact = False
        mock_marker2.wiki_page = True

        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.all_for_guild = AsyncMock(return_value=[mock_marker1, mock_marker2])

            response = await client.get(f'/api/guilds/{TEST_GUILD}/markers')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'markers' in data
            assert len(data['markers']) == 2
            assert data['markers'][0]['year'] == 1

    TEST_CHANNEL_ID = 666666

    @pytest.mark.asyncio
    async def test_get_marker_specific(self, client):
        """Test GET /api/guilds/<id>/markers/<year>/<channel> returns specific marker"""
        mock_marker = MagicMock()
        mock_marker.guild = TEST_GUILD
        mock_marker.channel = self.TEST_CHANNEL_ID
        mock_marker.message = 123456789012345678
        mock_marker.year = 5
        mock_marker.exact = True
        mock_marker.wiki_page = False

        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.get = AsyncMock(return_value=mock_marker)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/markers/5/{self.TEST_CHANNEL_ID}')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['year'] == 5
            assert data['exact'] is True

    @pytest.mark.asyncio
    async def test_get_marker_not_found(self, client):
        """Test GET /api/guilds/<id>/markers/<year>/<channel> returns 404 for missing marker"""
        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.get = AsyncMock(return_value=None)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/markers/999/{self.TEST_CHANNEL_ID}')
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_marker_timestamp(self, client):
        """Test GET /api/guilds/<id>/markers/<year>/timestamp returns timestamp"""
        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.timestamp = AsyncMock(return_value=1704067200)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/markers/5/timestamp')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['timestamp'] == 1704067200

    @pytest.mark.asyncio
    async def test_get_marker_timestamp_not_found(self, client):
        """Test GET /api/guilds/<id>/markers/<year>/timestamp returns 404"""
        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.timestamp = AsyncMock(return_value=None)

            response = await client.get(f'/api/guilds/{TEST_GUILD}/markers/999/timestamp')
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_marker_missing_message(self, client):
        """Test POST /api/guilds/<id>/markers/<year>/<channel> returns 400 when message missing"""
        response = await client.post(f'/api/guilds/{TEST_GUILD}/markers/5/{self.TEST_CHANNEL_ID}', json={})
        assert response.status_code == 400

        data = await response.get_json()
        assert 'error' in data

    @pytest.mark.asyncio
    async def test_create_marker_no_data(self, client):
        """Test POST /api/guilds/<id>/markers/<year>/<channel> returns 400 when no body"""
        response = await client.post(f'/api/guilds/{TEST_GUILD}/markers/5/{self.TEST_CHANNEL_ID}')
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_marker_db_error(self, client):
        """Test POST /api/guilds/<id>/markers/<year>/<channel> returns 500 on DB error"""
        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.get = AsyncMock(side_effect=Exception('DB connection lost'))

            response = await client.post(f'/api/guilds/{TEST_GUILD}/markers/5/{self.TEST_CHANNEL_ID}', json={'message': '123456789012345678'})
            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_create_marker_unauthorized(self, client):
        """Test POST /api/guilds/<id>/markers/<year>/<channel> returns 403 for unauthorized guild"""
        response = await client.post(f'/api/guilds/999999/markers/5/{self.TEST_CHANNEL_ID}', json={'message': '123456789012345678'})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_marker_not_found(self, client):
        """Test DELETE /api/guilds/<id>/markers/<year>/<channel> returns 404 when marker missing"""
        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.get = AsyncMock(return_value=None)

            response = await client.delete(f'/api/guilds/{TEST_GUILD}/markers/999/{self.TEST_CHANNEL_ID}')
            assert response.status_code == 404

            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_delete_marker_db_error(self, client):
        """Test DELETE /api/guilds/<id>/markers/<year>/<channel> returns 500 on DB error"""
        with patch('attubot.markers.YearMarker') as mock_marker_class:
            mock_marker_class.get = AsyncMock(side_effect=Exception('DB connection lost'))

            response = await client.delete(f'/api/guilds/{TEST_GUILD}/markers/5/{self.TEST_CHANNEL_ID}')
            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_delete_marker_unauthorized(self, client):
        """Test DELETE /api/guilds/<id>/markers/<year>/<channel> returns 403 for unauthorized guild"""
        response = await client.delete(f'/api/guilds/999999/markers/5/{self.TEST_CHANNEL_ID}')
        assert response.status_code == 403


# ========== Time/Calendar API Tests ==========


class TestTimeAPI:
    @pytest.mark.asyncio
    async def test_get_time_status(self, client):
        """Test GET /api/guilds/<id>/time returns time status"""
        with patch('attubot.calendar.get_year_status') as mock_status, patch('attubot.calendar.get_next_year') as mock_next:
            mock_status.return_value = (50, 5)  # 50 days elapsed, year 5
            mock_next.return_value = MagicMock(timestamp=MagicMock(return_value=1750000000), strftime=MagicMock(return_value='2025-06-15 17:00:00 UTC'))

            response = await client.get(f'/api/guilds/{TEST_GUILD}/time')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'current_year' in data
            assert 'elapsed_days' in data
            assert 'year_length' in data
            assert 'paused' in data
            assert data['current_year'] == 5

    @pytest.mark.asyncio
    async def test_get_time_status_guild_not_valid(self, client):
        """Test GET /api/guilds/<id>/time returns 200 for authorized guild with default/paused epoch"""
        response = await client.get(f'/api/guilds/{TEST_GUILD_2}/time')
        # Guild is authorized and has a config (paused=True by default), so time status is still valid
        assert response.status_code == 200

        data = await response.get_json()
        assert 'paused' in data
        assert data['paused'] is True

    @pytest.mark.asyncio
    async def test_get_year_span(self, client):
        """Test GET /api/guilds/<id>/time/year-span/<year> returns year span"""
        from attubot.calendar import AttuYearSpan

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705708800, duration=19)

        with patch('attubot.calendar.get_year_span', new=AsyncMock(return_value=mock_span)):
            response = await client.get(f'/api/guilds/{TEST_GUILD}/time/year-span/5')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['year'] == 5
            assert data['start_time'] == 1704067200
            assert data['duration'] == 19


# ========== Admin Stats API Tests ==========


class TestAdminStatsAPI:
    @pytest.mark.asyncio
    async def test_get_admin_stats(self, client):
        """Test GET /api/admin/stats returns system statistics"""
        with patch('attubot.years.Year') as mock_year, patch('attubot.markers.YearMarker') as mock_marker, patch('attubot.web.routes.db') as mock_db, patch('attubot.starboard._get_repo', side_effect=RuntimeError('not initialized')):
            mock_year.total = AsyncMock(side_effect=[10, 5])  # Called twice for 2 guilds
            mock_marker.total = AsyncMock(side_effect=[20, 8])
            mock_db.get_db.side_effect = RuntimeError('not connected')

            response = await client.get('/api/admin/stats')
            assert response.status_code == 200

            data = await response.get_json()
            assert 'guilds' in data
            assert 'data' in data
            assert 'system' in data
            assert data['guilds']['total'] == 2
            assert data['guilds']['configured'] == 1

    @pytest.mark.asyncio
    async def test_get_admin_stats_db_not_connected(self, client):
        """Test GET /api/admin/stats handles disconnected database"""
        with patch('attubot.years.Year') as mock_year, patch('attubot.markers.YearMarker') as mock_marker, patch('attubot.web.routes.db') as mock_db, patch('attubot.starboard._get_repo', side_effect=RuntimeError('not initialized')):
            mock_year.total = AsyncMock(return_value=0)
            mock_marker.total = AsyncMock(return_value=0)
            mock_db.get_db.side_effect = RuntimeError('not connected')

            response = await client.get('/api/admin/stats')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['system']['db_connected'] is False


# ========== Page Routes Tests ==========


class TestPageRoutes:
    @pytest.mark.asyncio
    async def test_years_page_authorized(self, client):
        """Test GET /guild/<id>/years renders years page"""
        response = await client.get(f'/guild/{TEST_GUILD}/years')
        assert response.status_code == 200
        html = await response.get_data(as_text=True)
        assert 'Year' in html

    @pytest.mark.asyncio
    async def test_years_page_unauthorized(self, client):
        """Test GET /guild/<id>/years returns 403 for unauthorized guild"""
        response = await client.get('/guild/999999/years')
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_markers_page_authorized(self, client):
        """Test GET /guild/<id>/markers renders markers page"""
        response = await client.get(f'/guild/{TEST_GUILD}/markers')
        assert response.status_code == 200
        html = await response.get_data(as_text=True)
        assert 'Marker' in html

    @pytest.mark.asyncio
    async def test_markers_page_unauthorized(self, client):
        """Test GET /guild/<id>/markers returns 403 for unauthorized guild"""
        response = await client.get('/guild/999999/markers')
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_time_page_authorized(self, client):
        """Test GET /guild/<id>/time renders time status page"""
        response = await client.get(f'/guild/{TEST_GUILD}/time')
        assert response.status_code == 200
        html = await response.get_data(as_text=True)
        assert 'Time' in html or 'Epoch' in html

    @pytest.mark.asyncio
    async def test_time_page_unauthorized(self, client):
        """Test GET /guild/<id>/time returns 403 for unauthorized guild"""
        response = await client.get('/guild/999999/time')
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_stats_page(self, client):
        """Test GET /admin/stats renders admin statistics page"""
        response = await client.get('/admin/stats')
        assert response.status_code == 200
        html = await response.get_data(as_text=True)
        assert 'Statistics' in html or 'Stats' in html or 'Guilds' in html


# ========== Guild Info API Tests ==========


class TestGuildInfoAPI:
    @pytest.mark.asyncio
    async def test_get_guild_info_success(self, client):
        """Test GET /api/guilds/<id>/info returns guild name and icon"""
        mock_info = {
            'id': str(TEST_GUILD),
            'name': 'Test Server',
            'icon_url': 'https://cdn.discordapp.com/icons/123/abc.png',
        }
        with patch('attubot.web.routes.get_guild_info', new=AsyncMock(return_value=mock_info)):
            response = await client.get(f'/api/guilds/{TEST_GUILD}/info')
            assert response.status_code == 200

            data = await response.get_json()
            assert data['name'] == 'Test Server'
            assert data['id'] == str(TEST_GUILD)
            assert 'icon_url' in data

    @pytest.mark.asyncio
    async def test_get_guild_info_fetch_failure(self, client):
        """Test GET /api/guilds/<id>/info returns 500 when Discord fetch fails"""
        with patch('attubot.web.routes.get_guild_info', new=AsyncMock(return_value=None)):
            response = await client.get(f'/api/guilds/{TEST_GUILD}/info')
            assert response.status_code == 500

            data = await response.get_json()
            assert 'error' in data

    @pytest.mark.asyncio
    async def test_get_guild_info_unauthorized(self, client):
        """Test GET /api/guilds/<id>/info returns 403 for unauthorized guild"""
        response = await client.get('/api/guilds/999999/info')
        assert response.status_code == 403

        data = await response.get_json()
        assert 'error' in data
