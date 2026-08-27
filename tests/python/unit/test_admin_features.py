# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_admin_features | feature enable/disable endpoints."""

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
    """bridge returning a single guild; cache/reload methods are trackable."""
    bridge = MagicMock()
    bridge.get_guild_info = AsyncMock(return_value={'id': '111', 'name': 'Test Guild', 'icon_url': None})
    bridge.get_guild_channels = AsyncMock(return_value=[])
    bridge.get_guild_roles = AsyncMock(return_value=[])
    bridge.invalidate_guild_cache = AsyncMock()
    bridge.trigger_reload = AsyncMock()
    return bridge


@pytest.fixture
def sample_doc():
    """minimal GuildConfigDocument for the test guild."""
    from attu_models.documents import GuildConfigDocument

    return GuildConfigDocument(
        guild_id=111,
        channels={},
        epoch={'year': 1, 'rollover_minutes': 60},
        roles={},
        users={},
    )


@pytest.fixture
def client(mock_bridge, sample_doc):
    from attu_server.api.admin import router as admin_router
    from attu_server.config import AuthConfig, BridgeConfig, DatabaseConfig, GuildEntry, ServerConfig, WebAuthnConfig, WebConfig

    cfg = ServerConfig(
        database=DatabaseConfig(url='mongodb://localhost:27017', name='test'),
        web=WebConfig(secret_key='test-session-secret'),
        webauthn=WebAuthnConfig(),
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


def _make_repo_mock(doc, update_calls=None):
    """build a ConfigRepository mock; optionally record update_guild_field calls."""
    mock_repo = AsyncMock()
    mock_repo.get_guild = AsyncMock(return_value=doc)
    if update_calls is not None:

        async def record_update(guild_id, key, value):
            update_calls.append((guild_id, key, value))

        mock_repo.update_guild_field = record_update
    else:
        mock_repo.update_guild_field = AsyncMock()
    return mock_repo


# --- POST /admin/guilds/{slug}/features/{feature}/enable ---


def test_enable_feature_db_write(client, sample_doc):
    """enable records update_guild_field with the correct field path and enabled=True."""
    update_calls = []
    mock_repo = _make_repo_mock(sample_doc, update_calls=update_calls)
    with patch('attu_server.api.admin.features.ConfigRepository', return_value=mock_repo):
        r = client.post('/api/admin/guilds/test-guild/features/starboard/enable', headers=auth)
    assert r.status_code == 200
    assert r.json() == {'feature': 'starboard', 'enabled': True}
    assert update_calls == [(111, 'starboard.enabled', True)]


def test_enable_feature_bridge_calls(client, sample_doc, mock_bridge):
    """enable calls bridge.invalidate_guild_cache and bridge.trigger_reload after the db write."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.features.ConfigRepository', return_value=mock_repo):
        r = client.post('/api/admin/guilds/test-guild/features/starboard/enable', headers=auth)
    assert r.status_code == 200
    mock_bridge.invalidate_guild_cache.assert_awaited_once_with(111)
    mock_bridge.trigger_reload.assert_awaited_once_with('guild', 111)


def test_disable_feature_db_write(client, sample_doc):
    """disable records update_guild_field with enabled=False."""
    update_calls = []
    mock_repo = _make_repo_mock(sample_doc, update_calls=update_calls)
    with patch('attu_server.api.admin.features.ConfigRepository', return_value=mock_repo):
        r = client.post('/api/admin/guilds/test-guild/features/ccboard/disable', headers=auth)
    assert r.status_code == 200
    assert r.json() == {'feature': 'ccboard', 'enabled': False}
    assert update_calls == [(111, 'ccboard.enabled', False)]


def test_disable_feature_bridge_calls(client, sample_doc, mock_bridge):
    """disable calls bridge.invalidate_guild_cache and bridge.trigger_reload."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.features.ConfigRepository', return_value=mock_repo):
        r = client.post('/api/admin/guilds/test-guild/features/ccboard/disable', headers=auth)
    assert r.status_code == 200
    mock_bridge.invalidate_guild_cache.assert_awaited_once_with(111)
    mock_bridge.trigger_reload.assert_awaited_once_with('guild', 111)


def test_feature_enable_404_unknown_guild(client, sample_doc):
    """unknown guild slug returns 404 before any db or bridge calls."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.features.ConfigRepository', return_value=mock_repo):
        r = client.post('/api/admin/guilds/no-such-guild/features/starboard/enable', headers=auth)
    assert r.status_code == 404


def test_feature_enable_404_no_guild_config(client, mock_bridge):
    """guild in config but no doc in db returns 404."""
    mock_repo = _make_repo_mock(None)
    with patch('attu_server.api.admin.features.ConfigRepository', return_value=mock_repo):
        r = client.post('/api/admin/guilds/test-guild/features/starboard/enable', headers=auth)
    assert r.status_code == 404


def test_feature_toggle_401_without_key(client, sample_doc):
    """feature endpoints require a valid bearer token."""
    mock_repo = _make_repo_mock(sample_doc)
    with patch('attu_server.api.admin.features.ConfigRepository', return_value=mock_repo):
        r = client.post('/api/admin/guilds/test-guild/features/starboard/enable')
    assert r.status_code == 401
