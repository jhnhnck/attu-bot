# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_nova_admin | _AdminSession state transitions and slug resolution."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import MagicMock

import pytest
from nova_admin import _AdminSession


pytestmark = pytest.mark.unit


# --- helpers ---


def _resp(data, status=200):
    """build a mock httpx response with is_success, status_code, and json()."""
    r = MagicMock()
    r.is_success = status < 300
    r.status_code = status
    r.json.return_value = data
    r.text = repr(data)
    return r


def _session():
    """create a fresh _AdminSession with test credentials."""
    return _AdminSession(api_key='test-key', server_url='http://localhost:8000')


# --- get_guilds ---


def test_get_guilds_returns_list():
    session = _session()
    guilds = [{'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'}]
    client = MagicMock()
    client.request.return_value = _resp(guilds)

    result = session.get_guilds(client)

    assert result == guilds


def test_get_guilds_on_error_returns_empty():
    session = _session()
    client = MagicMock()
    client.request.return_value = _resp({'detail': 'unauthorized'}, status=401)

    result = session.get_guilds(client)

    assert result == []


# --- select_guild ---


def test_select_guild_success():
    session = _session()
    guilds = [{'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'}]
    channels = [{'id': '111001', 'name': 'general', 'slug': 'general', 'type': 'text_channel'}]
    roles = [{'id': '111010', 'name': 'Admin', 'slug': 'admin'}]

    def _side(method, url, **kwargs):
        if url.endswith('/api/admin/guilds'):
            return _resp(guilds)
        if url.endswith('/channels'):
            return _resp(channels)
        if url.endswith('/roles'):
            return _resp(roles)
        raise AssertionError(f'unexpected url: {url}')
    client = MagicMock()
    client.request.side_effect = _side

    result = session.select_guild(client, 'test-guild')

    assert result is True
    assert session.current_guild == guilds[0]
    assert session.channels == channels
    assert session.roles == roles


def test_select_guild_unknown_slug(capsys):
    session = _session()
    guilds = [{'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'}]
    client = MagicMock()
    client.request.return_value = _resp(guilds)

    result = session.select_guild(client, 'no-such-guild')

    assert result is False
    assert session.current_guild is None
    out = capsys.readouterr().out
    assert 'guild not found' in out
    assert 'no-such-guild' in out


def test_select_guild_channels_error_returns_false():
    session = _session()
    guilds = [{'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'}]

    def _side(method, url, **kwargs):
        if url.endswith('/api/admin/guilds'):
            return _resp(guilds)
        if url.endswith('/channels'):
            return _resp({'detail': 'not found'}, status=404)
        raise AssertionError(f'unexpected url: {url}')
    client = MagicMock()
    client.request.side_effect = _side

    result = session.select_guild(client, 'test-guild')

    assert result is False
    assert session.current_guild is None


def test_select_guild_sets_all_state():
    """select_guild populates current_guild, channels, and roles atomically on success."""
    session = _session()
    guilds = [
        {'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'},
        {'id': '222', 'name': 'Other Guild', 'slug': 'other-guild', 'role': 'secondary'},
    ]
    channels = [
        {'id': '111001', 'name': 'general', 'slug': 'general', 'type': 'text_channel'},
        {'id': '111002', 'name': 'announcements', 'slug': 'announcements', 'type': 'text_channel'},
    ]
    roles = [
        {'id': '111010', 'name': 'Admin', 'slug': 'admin'},
        {'id': '111011', 'name': 'Member', 'slug': 'member'},
    ]

    def _side(method, url, **kwargs):
        if url.endswith('/api/admin/guilds'):
            return _resp(guilds)
        if url.endswith('/channels'):
            return _resp(channels)
        if url.endswith('/roles'):
            return _resp(roles)
        raise AssertionError(f'unexpected url: {url}')
    client = MagicMock()
    client.request.side_effect = _side

    result = session.select_guild(client, 'other-guild')

    assert result is True
    assert session.current_guild == guilds[1]
    assert session.channels == channels
    assert session.roles == roles


# --- refresh ---


def test_refresh_updates_state():
    session = _session()
    session.current_guild = {'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'}
    session.channels = [{'id': '111001', 'name': 'general', 'slug': 'general', 'type': 'text_channel'}]
    session.roles = [{'id': '111010', 'name': 'Admin', 'slug': 'admin'}]

    new_channels = [
        {'id': '111001', 'name': 'general', 'slug': 'general', 'type': 'text_channel'},
        {'id': '111002', 'name': 'off-topic', 'slug': 'off-topic', 'type': 'text_channel'},
    ]
    new_roles = [
        {'id': '111010', 'name': 'Admin', 'slug': 'admin'},
        {'id': '111011', 'name': 'Member', 'slug': 'member'},
    ]

    def _side(method, url, **kwargs):
        if url.endswith('/channels'):
            return _resp(new_channels)
        if url.endswith('/roles'):
            return _resp(new_roles)
        raise AssertionError(f'unexpected url: {url}')
    client = MagicMock()
    client.request.side_effect = _side

    result = session.refresh(client)

    assert result is True
    assert session.channels == new_channels
    assert session.roles == new_roles


def test_refresh_no_guild_selected(capsys):
    session = _session()
    client = MagicMock()

    result = session.refresh(client)

    assert result is False
    client.request.assert_not_called()
    out = capsys.readouterr().out
    assert 'no guild selected' in out


def test_refresh_preserves_current_guild():
    """refresh replaces channels/roles but does not modify current_guild."""
    session = _session()
    original_guild = {'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'}
    session.current_guild = original_guild
    session.channels = []
    session.roles = []

    def _side(method, url, **kwargs):
        if url.endswith('/channels'):
            return _resp([{'id': '111001', 'name': 'general', 'slug': 'general', 'type': 'text_channel'}])
        if url.endswith('/roles'):
            return _resp([])
        raise AssertionError(f'unexpected url: {url}')
    client = MagicMock()
    client.request.side_effect = _side

    session.refresh(client)

    assert session.current_guild == original_guild


# --- resolve_channel_slug ---


def test_resolve_channel_slug_found():
    session = _session()
    session.channels = [
        {'id': '111001', 'name': 'general', 'slug': 'general', 'type': 'text_channel'},
        {'id': '111002', 'name': 'announcements', 'slug': 'announcements', 'type': 'text_channel'},
    ]
    result = session.resolve_channel_slug('general')
    assert result == session.channels[0]


def test_resolve_channel_slug_not_found():
    session = _session()
    session.channels = [{'id': '111001', 'name': 'general', 'slug': 'general', 'type': 'text_channel'}]
    result = session.resolve_channel_slug('no-such-channel')
    assert result is None


def test_resolve_channel_slug_empty_cache():
    session = _session()
    result = session.resolve_channel_slug('general')
    assert result is None


# --- resolve_role_slug ---


def test_resolve_role_slug_found():
    session = _session()
    session.roles = [
        {'id': '111010', 'name': 'Admin', 'slug': 'admin'},
        {'id': '111011', 'name': 'Member', 'slug': 'member'},
    ]
    result = session.resolve_role_slug('member')
    assert result == session.roles[1]


def test_resolve_role_slug_not_found():
    session = _session()
    session.roles = [{'id': '111010', 'name': 'Admin', 'slug': 'admin'}]
    result = session.resolve_role_slug('no-such-role')
    assert result is None


def test_resolve_role_slug_empty_cache():
    session = _session()
    result = session.resolve_role_slug('admin')
    assert result is None


# --- require_guild ---


def test_require_guild_false_when_none(capsys):
    session = _session()
    result = session.require_guild()
    assert result is False
    out = capsys.readouterr().out
    assert 'no guild selected' in out


def test_require_guild_true_when_set():
    session = _session()
    session.current_guild = {'id': '111', 'name': 'Test Guild', 'slug': 'test-guild', 'role': 'primary'}
    result = session.require_guild()
    assert result is True
