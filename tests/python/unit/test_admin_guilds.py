# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_admin_guilds | slug helpers and guild admin endpoints."""

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


# --- load_config wiring ---


def test_load_config_wires_api_keys_and_guilds(tmp_path):
    """load_config reads auth.api_keys and [[guilds]] from TOML."""
    from attu_server.config import load_config

    toml_content = """\
[database]
url = "mongodb://localhost:27017/test"
name = "test"

[auth]
api_keys = ["secret-1", "secret-2"]

[auth.web]
secret_key = "test-web-secret"

[bridge]
secret = "test-bridge-secret"

[[guilds]]
id = 111111111111111111
role = "primary"

[[guilds]]
id = 222222222222222222
role = "secondary"
"""
    config_file = tmp_path / 'attu-bot.toml'
    config_file.write_text(toml_content)

    cfg = load_config(config_file)
    assert cfg.auth.api_keys == ['secret-1', 'secret-2']
    assert len(cfg.guilds) == 2
    assert cfg.guilds[0].id == 111111111111111111
    assert cfg.guilds[0].role == 'primary'
    assert cfg.guilds[1].id == 222222222222222222
    assert cfg.guilds[1].role == 'secondary'


def test_load_config_defaults_when_sections_absent(tmp_path):
    """auth.api_keys and guilds default to [] when sections are missing."""
    from attu_server.config import load_config

    toml_content = """\
[database]
url = "mongodb://localhost:27017/test"
name = "test"

[auth.web]
secret_key = "test-web-secret"

[bridge]
secret = "test-bridge-secret"
"""
    config_file = tmp_path / 'attu-bot.toml'
    config_file.write_text(toml_content)

    cfg = load_config(config_file)
    assert cfg.auth.api_keys == []
    assert cfg.guilds == []


# --- slug function tests ---


def test_slugify_basic():
    from attu_server.api.admin.slugs import slugify

    assert slugify('Hello World') == 'hello-world'


def test_slugify_strips_non_alphanum():
    from attu_server.api.admin.slugs import slugify

    assert slugify('Test!@#$Guild') == 'testguild'


def test_slugify_collapses_dashes():
    from attu_server.api.admin.slugs import slugify

    assert slugify('Hello--World') == 'hello-world'
    assert slugify('a  b') == 'a-b'  # double space -> double dash -> collapsed


def test_slugify_preserves_existing_dash():
    from attu_server.api.admin.slugs import slugify

    assert slugify('my-guild') == 'my-guild'


def test_slugify_lowercase():
    from attu_server.api.admin.slugs import slugify

    assert slugify('UPPER') == 'upper'


def test_slugify_alphanumeric():
    from attu_server.api.admin.slugs import slugify

    assert slugify('Guild 42') == 'guild-42'


def test_make_slug_map_no_collision():
    from attu_server.api.admin.slugs import make_slug_map

    items = [{'id': '1', 'name': 'Alpha'}, {'id': '2', 'name': 'Beta'}]
    result = make_slug_map(items)
    assert set(result.keys()) == {'alpha', 'beta'}
    assert result['alpha']['id'] == '1'
    assert result['beta']['id'] == '2'


def test_make_slug_map_two_collision():
    from attu_server.api.admin.slugs import make_slug_map

    items = [{'id': '1', 'name': 'Test Guild'}, {'id': '2', 'name': 'Test Guild'}]
    result = make_slug_map(items)
    assert 'test-guild' in result
    assert 'test-guild-2' in result
    assert result['test-guild']['id'] == '1'
    assert result['test-guild-2']['id'] == '2'


def test_make_slug_map_three_collision():
    from attu_server.api.admin.slugs import make_slug_map

    items = [
        {'id': '1', 'name': 'Same'},
        {'id': '2', 'name': 'Same'},
        {'id': '3', 'name': 'Same'},
    ]
    result = make_slug_map(items)
    assert 'same' in result
    assert 'same-2' in result
    assert 'same-3' in result
    assert result['same']['id'] == '1'
    assert result['same-2']['id'] == '2'
    assert result['same-3']['id'] == '3'


# --- endpoint fixtures ---


@pytest.fixture
def mock_bridge():
    guild_data = {
        111: {'id': '111', 'name': 'Test Guild', 'icon_url': None},
        222: {'id': '222', 'name': 'Other Guild', 'icon_url': None},
    }
    bridge = MagicMock()
    bridge.get_guild_info = AsyncMock(side_effect=lambda gid: guild_data[gid])
    bridge.get_guild_channels = AsyncMock(
        return_value=[
            {'id': '111001', 'name': 'general', 'type': 'text_channel', 'position': 0, 'category_id': None, 'is_thread': False},
            {'id': '111002', 'name': 'announcements', 'type': 'text_channel', 'position': 1, 'category_id': None, 'is_thread': False},
        ]
    )
    bridge.get_guild_roles = AsyncMock(
        return_value=[
            {'id': '111010', 'name': 'Admin', 'color': '0x0', 'position': 2, 'managed': False, 'is_default': False},
            {'id': '111011', 'name': 'Member', 'color': '0x0', 'position': 1, 'managed': False, 'is_default': False},
        ]
    )
    return bridge


@pytest.fixture
def client(mock_bridge):
    from attu_server.api.admin import router as admin_router
    from attu_server.config import AuthConfig, BridgeConfig, DatabaseConfig, GuildEntry, ServerConfig, WebConfig

    cfg = ServerConfig(
        database=DatabaseConfig(url='mongodb://localhost:27017', name='test'),
        web=WebConfig(secret_key='test-session-secret'),

        bridge=BridgeConfig(secret='test-bridge-secret'),
        auth=AuthConfig(api_keys=['valid-key']),
        guilds=[GuildEntry(id=111, role='primary'), GuildEntry(id=222, role='secondary')],
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


# --- GET /admin/guilds ---


def test_list_guilds_returns_slugged_list(client):
    r = client.get('/api/admin/guilds', headers={'Authorization': 'Bearer valid-key'})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    slugs = {g['slug'] for g in data}
    assert 'test-guild' in slugs
    assert 'other-guild' in slugs
    by_slug = {g['slug']: g for g in data}
    assert by_slug['test-guild']['role'] == 'primary'
    assert by_slug['other-guild']['role'] == 'secondary'


def test_list_guilds_calls_bridge_once_per_guild(client, mock_bridge):
    r = client.get('/api/admin/guilds', headers={'Authorization': 'Bearer valid-key'})
    assert r.status_code == 200
    # len(config.guilds) == 2
    assert mock_bridge.get_guild_info.call_count == 2


def test_list_guilds_401_without_key(client):
    r = client.get('/api/admin/guilds')
    assert r.status_code == 401


# --- GET /admin/guilds/{slug}/channels ---


def test_list_guild_channels_200(client):
    r = client.get('/api/admin/guilds/test-guild/channels', headers={'Authorization': 'Bearer valid-key'})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 2
    slugs = {ch['slug'] for ch in data}
    assert 'general' in slugs
    assert 'announcements' in slugs
    for ch in data:
        assert 'id' in ch
        assert 'name' in ch
        assert 'slug' in ch
        assert 'type' in ch


def test_list_guild_channels_404_unknown_slug(client):
    r = client.get('/api/admin/guilds/does-not-exist/channels', headers={'Authorization': 'Bearer valid-key'})
    assert r.status_code == 404


# --- GET /admin/guilds/{slug}/roles ---


def test_list_guild_roles_200(client):
    r = client.get('/api/admin/guilds/test-guild/roles', headers={'Authorization': 'Bearer valid-key'})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 2
    slugs = {role['slug'] for role in data}
    assert 'admin' in slugs
    assert 'member' in slugs
    for role in data:
        assert 'id' in role
        assert 'name' in role
        assert 'slug' in role


def test_list_guild_roles_404_unknown_slug(client):
    r = client.get('/api/admin/guilds/does-not-exist/roles', headers={'Authorization': 'Bearer valid-key'})
    assert r.status_code == 404
