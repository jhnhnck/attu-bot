# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_admin_reload | reload trigger endpoints."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware


pytestmark = pytest.mark.unit

auth = {'Authorization': 'Bearer valid-key'}


# --- fixtures ---


@pytest.fixture
def mock_bridge():
    """bridge returning a single guild; trigger_reload is trackable."""
    bridge = MagicMock()
    bridge.get_guild_info = AsyncMock(return_value={'id': '111', 'name': 'Test Guild', 'icon_url': None})
    bridge.get_guild_channels = AsyncMock(return_value=[])
    bridge.get_guild_roles = AsyncMock(return_value=[])
    bridge.trigger_reload = AsyncMock()
    return bridge


@pytest.fixture
def client(mock_bridge):
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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = cfg
        app.state.bridge = mock_bridge
        yield

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key='test-session-secret')
    app.include_router(admin_router, prefix='/api')

    with TestClient(app) as tc:
        yield tc


# --- POST /admin/reload/guild ---


def test_reload_guild_resolves_slug_and_calls_bridge(client, mock_bridge):
    """reload/guild resolves the slug to a guild id and calls trigger_reload('guild', id)."""
    r = client.post('/api/admin/reload/guild', json={'guild_slug': 'test-guild'}, headers=auth)
    assert r.status_code == 200
    assert r.json() == {'ok': True}
    mock_bridge.trigger_reload.assert_awaited_once_with('guild', 111)


def test_reload_guild_404_unknown_slug(client):
    """reload/guild returns 404 for an unrecognized guild slug."""
    r = client.post('/api/admin/reload/guild', json={'guild_slug': 'no-such-guild'}, headers=auth)
    assert r.status_code == 404


def test_reload_guild_uses_resolve_guild_id(client, mock_bridge):
    """verify slug resolution uses the slug map - bridge.get_guild_info is called to build it."""
    client.post('/api/admin/reload/guild', json={'guild_slug': 'test-guild'}, headers=auth)
    # _build_guild_slug_map calls get_guild_info once per configured guild
    assert mock_bridge.get_guild_info.call_count == 1


# --- POST /admin/reload/theme ---


def test_reload_theme_calls_bridge(client, mock_bridge):
    """reload/theme calls trigger_reload('theme') with no guild_id."""
    r = client.post('/api/admin/reload/theme', headers=auth)
    assert r.status_code == 200
    assert r.json() == {'ok': True}
    mock_bridge.trigger_reload.assert_awaited_once_with('theme')


# --- POST /admin/reload/system ---


def test_reload_system_calls_bridge(client, mock_bridge):
    """reload/system calls trigger_reload('system') with no guild_id."""
    r = client.post('/api/admin/reload/system', headers=auth)
    assert r.status_code == 200
    assert r.json() == {'ok': True}
    mock_bridge.trigger_reload.assert_awaited_once_with('system')


def test_reload_401_without_key(client):
    """reload endpoints require a valid bearer token."""
    r = client.post('/api/admin/reload/theme')
    assert r.status_code == 401
