# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_admin_ops | bridge ops forwarding endpoints."""

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
    bridge = MagicMock()
    bridge.get_guild_info = AsyncMock(return_value={'id': '111', 'name': 'Test Guild', 'icon_url': None})
    bridge.get_guild_channels = AsyncMock(return_value=[])
    bridge.get_guild_roles = AsyncMock(return_value=[])
    bridge.get_op = AsyncMock(return_value={'ok': True})
    bridge.post_op = AsyncMock(return_value={'ok': True})
    return bridge


@pytest.fixture
def client(mock_bridge):
    from attu_server.api.admin import router as admin_router
    from attu_server.config import AuthConfig, BridgeConfig, DatabaseConfig, GuildEntry, ServerConfig

    cfg = ServerConfig(
        database=DatabaseConfig(url='mongodb://localhost:27017', name='test'),
        bridge=BridgeConfig(secret='test-bridge-secret'),
        auth=AuthConfig(api_keys=['valid-key'], secret_key='test-session-secret'),
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


# --- global ops (no guild required) ---


def test_info_version_forwards_to_bridge(client, mock_bridge):
    r = client.get('/api/admin/ops/info/version', headers=auth)
    assert r.status_code == 200
    mock_bridge.get_op.assert_awaited_once_with('/bridge/ops/info/version')


def test_info_scheduler_forwards_to_bridge(client, mock_bridge):
    r = client.get('/api/admin/ops/info/scheduler', headers=auth)
    assert r.status_code == 200
    mock_bridge.get_op.assert_awaited_once_with('/bridge/ops/info/scheduler')


def test_trigger_logo_forwards_to_bridge(client, mock_bridge):
    r = client.post('/api/admin/ops/trigger/logo', headers=auth)
    assert r.status_code == 200
    mock_bridge.post_op.assert_awaited_once_with('/bridge/ops/trigger/logo')


def test_trigger_emoji_sync_forwards_to_bridge(client, mock_bridge):
    r = client.post('/api/admin/ops/trigger/emoji-sync', headers=auth)
    assert r.status_code == 200
    mock_bridge.post_op.assert_awaited_once_with('/bridge/ops/trigger/emoji-sync')


def test_inspect_message_forwards_params(client, mock_bridge):
    r = client.get('/api/admin/ops/inspect/message?guild_id=111&channel_id=222&message_id=333', headers=auth)
    assert r.status_code == 200
    mock_bridge.get_op.assert_awaited_once_with(
        '/bridge/ops/inspect/message',
        params={'guild_id': 111, 'channel_id': 222, 'message_id': 333},
    )


def test_global_ops_require_auth(client):
    r = client.get('/api/admin/ops/info/version')
    assert r.status_code == 401


# --- guild-scoped ops ---


def test_backfill_channel_forwards_to_bridge(client, mock_bridge):
    r = client.post('/api/admin/ops/test-guild/backfill/channel', json={'channel_id': 111001}, headers=auth)
    assert r.status_code == 200
    mock_bridge.post_op.assert_awaited_once_with(
        '/bridge/ops/backfill/channel',
        {'guild_id': 111, 'channel_id': 111001},
    )


def test_backfill_guild_forwards_to_bridge(client, mock_bridge):
    r = client.post('/api/admin/ops/test-guild/backfill/guild', json={'lookback_days': 3}, headers=auth)
    assert r.status_code == 200
    mock_bridge.post_op.assert_awaited_once_with(
        '/bridge/ops/backfill/guild',
        {'guild_id': 111, 'lookback_days': 3},
    )


def test_ccboard_regen_forwards_to_bridge(client, mock_bridge):
    r = client.post('/api/admin/ops/test-guild/ccboard/regen', headers=auth)
    assert r.status_code == 200
    mock_bridge.post_op.assert_awaited_once_with('/bridge/ops/ccboard/regen', {'guild_id': 111})


def test_ccboard_purge_forwards_to_bridge(client, mock_bridge):
    r = client.post('/api/admin/ops/test-guild/ccboard/purge', json={'message_id': 9999}, headers=auth)
    assert r.status_code == 200
    mock_bridge.post_op.assert_awaited_once_with(
        '/bridge/ops/ccboard/purge',
        {'guild_id': 111, 'message_id': 9999},
    )


def test_ccboard_reactions_forwards_params(client, mock_bridge):
    r = client.get('/api/admin/ops/test-guild/ccboard/reactions?message_id=9999', headers=auth)
    assert r.status_code == 200
    mock_bridge.get_op.assert_awaited_once_with(
        '/bridge/ops/ccboard/reactions',
        params={'guild_id': 111, 'message_id': 9999},
    )


def test_guild_op_404_unknown_slug(client, mock_bridge):
    r = client.post('/api/admin/ops/no-such-guild/ccboard/regen', headers=auth)
    assert r.status_code == 404
    mock_bridge.post_op.assert_not_awaited()



def test_trigger_year_links_forwards_to_bridge(client, mock_bridge):
    r = client.post('/api/admin/ops/test-guild/trigger/year-links', headers=auth)
    assert r.status_code == 200
    mock_bridge.post_op.assert_awaited_once_with('/bridge/ops/trigger/year-links', {'guild_id': 111})


def test_info_epoch_forwards_to_bridge(client, mock_bridge):
    r = client.get('/api/admin/ops/test-guild/info/epoch', headers=auth)
    assert r.status_code == 200
    mock_bridge.get_op.assert_awaited_once_with('/bridge/ops/info/epoch', params={'guild_id': 111})
