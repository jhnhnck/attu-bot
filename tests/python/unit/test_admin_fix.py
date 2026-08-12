# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_admin_fix | fix/maintenance operation endpoints."""

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
    """bridge returning a single guild with a configurable post_fix response."""
    bridge = MagicMock()
    bridge.get_guild_info = AsyncMock(return_value={'id': '111', 'name': 'Test Guild', 'icon_url': None})
    bridge.get_guild_channels = AsyncMock(return_value=[])
    bridge.get_guild_roles = AsyncMock(return_value=[])
    bridge.post_fix = AsyncMock()
    return bridge


def _make_mock_response(status_code: int) -> MagicMock:
    """build a minimal httpx.Response-like mock."""
    r = MagicMock()
    r.status_code = status_code
    r.raise_for_status = MagicMock()
    return r


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


# --- POST /admin/guilds/{slug}/fix/recalculate-starboard ---


def test_fix_recalculate_starboard_200(client, mock_bridge):
    """when the bridge returns 200, the endpoint returns 200 ok."""
    mock_bridge.post_fix = AsyncMock(return_value=_make_mock_response(200))
    r = client.post('/api/admin/guilds/test-guild/fix/recalculate-starboard', headers=auth)
    assert r.status_code == 200
    assert r.json() == {'ok': True}
    mock_bridge.post_fix.assert_awaited_once_with('recalculate-starboard', guild_id=111)


def test_fix_recalculate_starboard_501_on_bridge_404(client, mock_bridge):
    """when the bridge returns 404 (endpoint not yet implemented), returns 501 with the expected body."""
    mock_bridge.post_fix = AsyncMock(return_value=_make_mock_response(404))
    r = client.post('/api/admin/guilds/test-guild/fix/recalculate-starboard', headers=auth)
    assert r.status_code == 501
    data = r.json()
    assert data['detail'] == 'bridge fix endpoint not yet available'
    assert data['operation'] == 'recalculate-starboard'


def test_fix_recalculate_starboard_404_unknown_guild(client, mock_bridge):
    """unrecognized guild slug returns 404 before calling the bridge."""
    r = client.post('/api/admin/guilds/no-such-guild/fix/recalculate-starboard', headers=auth)
    assert r.status_code == 404
    mock_bridge.post_fix.assert_not_awaited()


def test_fix_401_without_key(client):
    """fix endpoints require a valid bearer token."""
    r = client.post('/api/admin/guilds/test-guild/fix/recalculate-starboard')
    assert r.status_code == 401
