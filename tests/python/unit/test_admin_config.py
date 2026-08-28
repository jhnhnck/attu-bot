# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_admin_config | guild config get/patch endpoints."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware


pytestmark = pytest.mark.unit

auth = {'Authorization': 'Bearer valid-key'}


# --- fixtures ---


@pytest.fixture
def mock_bridge():
    """bridge returning a single guild with two channels and one role."""
    channels = [
        {'id': '111001', 'name': 'general', 'type': 'text_channel', 'position': 0, 'category_id': None, 'is_thread': False},
        {'id': '111002', 'name': 'announcements', 'type': 'text_channel', 'position': 1, 'category_id': None, 'is_thread': False},
    ]
    roles = [
        {'id': '111010', 'name': 'Admin', 'color': '0x0', 'position': 2, 'managed': False, 'is_default': False},
    ]
    bridge = MagicMock()
    bridge.get_guild_info = AsyncMock(return_value={'id': '111', 'name': 'Test Guild', 'icon_url': None})
    bridge.get_guild_channels = AsyncMock(return_value=channels)
    bridge.get_guild_roles = AsyncMock(return_value=roles)
    bridge.invalidate_guild_cache = AsyncMock()
    bridge.trigger_reload = AsyncMock()
    return bridge


@pytest.fixture
def sample_doc():
    """real GuildConfigDocument with known field values for assertion."""
    from attu_models.documents import GuildConfigDocument

    return GuildConfigDocument(
        guild_id=111,
        channels={'log_channel': 111001, 'announcement_channel': 111002},
        epoch={'year': 100, 'rollover_minutes': 1020},
        roles={'announcements_role': 111010},
        users={},
        starboard={'channel': 111001, 'log_channel': 111001, 'threshold': 3},
        ccboard={'channel': 111002, 'threshold': 5},
    )


@pytest.fixture
def client(mock_bridge, sample_doc):
    from attu_server.api.admin import router as admin_router
    from attu_server.config import AuthConfig, BridgeConfig, DatabaseConfig, GuildEntry, ServerConfig, WebConfig

    cfg = ServerConfig(
        database=DatabaseConfig(url='mongodb://localhost:27017', name='test'),
        web=WebConfig(secret_key='test-session-secret'),

        bridge=BridgeConfig(secret='test-bridge-secret'),
        auth=AuthConfig(api_keys=['valid-key']),
        guilds=[GuildEntry(id=111, role='primary')],
    )

    mock_storage = MagicMock()
    mock_storage.get_db = MagicMock(return_value=MagicMock())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = cfg
        app.state.bridge = mock_bridge
        app.state.storage = mock_storage
        yield

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key='test-session-secret')
    app.include_router(admin_router, prefix='/api')

    with TestClient(app) as tc:
        yield tc


def _make_repo_mock(doc, update_field=None):
    """build a ConfigRepository mock with get_guild returning doc and optional update_guild_field side-effect."""
    mock_repo = AsyncMock()
    mock_repo.get_guild = AsyncMock(return_value=doc)
    mock_repo.update_guild_field = update_field if update_field is not None else AsyncMock()
    return mock_repo


# --- GET /admin/guilds/{slug}/config/{key} ---


def test_get_config_roundtrip(client, sample_doc):
    """GET returns the stored value for a real GuildConfigDocument field."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.get('/api/admin/guilds/test-guild/config/starboard.channel', headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data['key'] == 'starboard.channel'
    assert data['value'] == 111001


def test_get_config_top_level_field(client, sample_doc):
    """GET on a top-level model field (guild_id) returns its value."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.get('/api/admin/guilds/test-guild/config/guild_id', headers=auth)
    assert r.status_code == 200
    assert r.json()['value'] == 111


def test_get_config_422_unknown_top_level(client, sample_doc):
    """GET with a key segment not in GuildConfigDocument.model_fields returns 422."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.get('/api/admin/guilds/test-guild/config/nonexistent_section.foo', headers=auth)
    assert r.status_code == 422


def test_get_config_404_unknown_guild(client, sample_doc):
    """GET with an unrecognized guild slug returns 404."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.get('/api/admin/guilds/no-such-guild/config/starboard.channel', headers=auth)
    assert r.status_code == 404


# --- PATCH /admin/guilds/{slug}/config/{key} ---


def test_patch_config_roundtrip(client, sample_doc, mock_bridge):
    """PATCH sets a field and returns the new value; update_guild_field is called with the right args."""
    update_calls = []

    async def record_update(guild_id, key, value):
        update_calls.append((guild_id, key, value))

    mock_repo = _make_repo_mock(sample_doc, update_field=record_update)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.patch(
            '/api/admin/guilds/test-guild/config/starboard.threshold',
            json={'value': 7},
            headers=auth,
        )
    assert r.status_code == 200
    data = r.json()
    assert data['key'] == 'starboard.threshold'
    assert data['value'] == 7
    assert update_calls == [(111, 'starboard.threshold', 7)]


def test_patch_config_slug_to_snowflake(client, sample_doc, mock_bridge):
    """PATCH a *_channel field with a channel slug; stored value is the integer snowflake."""
    update_calls = []

    async def record_update(guild_id, key, value):
        update_calls.append((guild_id, key, value))

    mock_repo = _make_repo_mock(sample_doc, update_field=record_update)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.patch(
            '/api/admin/guilds/test-guild/config/starboard.log_channel',
            json={'value': 'general'},
            headers=auth,
        )
    assert r.status_code == 200
    data = r.json()
    # 'general' slug resolved to snowflake 111001
    assert data['value'] == 111001
    assert update_calls == [(111, 'starboard.log_channel', 111001)]


def test_patch_config_slug_to_snowflake_not_slug(client, sample_doc, mock_bridge):
    """PATCH a *_channel field with a raw integer string; stored as the integer."""
    update_calls = []

    async def record_update(guild_id, key, value):
        update_calls.append((guild_id, key, value))

    mock_repo = _make_repo_mock(sample_doc, update_field=record_update)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.patch(
            '/api/admin/guilds/test-guild/config/starboard.log_channel',
            json={'value': '111001'},
            headers=auth,
        )
    assert r.status_code == 200
    assert r.json()['value'] == 111001


def test_patch_config_422_invalid_key_path(client, sample_doc):
    """PATCH with a top-level key not in model_fields returns 422."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.patch(
            '/api/admin/guilds/test-guild/config/bad_section.field',
            json={'value': 42},
            headers=auth,
        )
    assert r.status_code == 422


def test_patch_config_422_type_mismatch(client, sample_doc, mock_bridge):
    """PATCH a *_channel field with a value that is neither a slug nor parseable as int returns 422.

    no bool field exists in GuildConfigDocument, so this tests the _channel coercion path as
    the equivalent type-mismatch case.
    """
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.patch(
            '/api/admin/guilds/test-guild/config/starboard.log_channel',
            json={'value': 'not-a-number-or-slug'},
            headers=auth,
        )
    assert r.status_code == 422


def test_patch_config_404_unknown_guild(client, sample_doc):
    """PATCH with an unrecognized guild slug returns 404."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.patch(
            '/api/admin/guilds/no-such-guild/config/starboard.threshold',
            json={'value': 10},
            headers=auth,
        )
    assert r.status_code == 404


def test_patch_config_calls_bridge_invalidate_and_reload(client, sample_doc, mock_bridge):
    """every successful PATCH calls bridge.invalidate_guild_cache and bridge.trigger_reload."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.config_routes.ConfigRepository', return_value=mock_repo):
        r = client.patch(
            '/api/admin/guilds/test-guild/config/starboard.threshold',
            json={'value': 5},
            headers=auth,
        )
    assert r.status_code == 200
    mock_bridge.invalidate_guild_cache.assert_awaited_once_with(111)
    mock_bridge.trigger_reload.assert_awaited_once_with('guild', 111)
