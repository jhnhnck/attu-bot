"""
AttuBot - Unit Tests for Discord Integration (Web Module)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from doom_bot.web.discord_integration import (
    DiscordCache,
    _cache,
    get_guild_channels,
    get_guild_info,
    get_guild_roles,
    get_user_info,
    invalidate_guild_cache,
)


pytestmark = pytest.mark.unit


# ============================================================
# DiscordCache
# ============================================================


class TestDiscordCacheGet:
    """unit: DiscordCache.get() returns cached values or None"""

    def test_returns_none_for_missing_key(self):
        cache = DiscordCache(ttl=300)
        assert cache.get('nonexistent') is None

    def test_returns_value_for_valid_key(self):
        cache = DiscordCache(ttl=300)
        cache.set('mykey', {'data': 42})
        assert cache.get('mykey') == {'data': 42}

    def test_returns_none_for_expired_key(self):
        cache = DiscordCache(ttl=10)
        # set a value with a fake timestamp in the past
        cache.cache['old'] = (time.time() - 1, 'stale')
        assert cache.get('old') is None

    def test_expired_key_is_deleted(self):
        cache = DiscordCache(ttl=10)
        cache.cache['old'] = (time.time() - 1, 'stale')
        cache.get('old')
        assert 'old' not in cache.cache


class TestDiscordCacheSet:
    """unit: DiscordCache.set() stores value with expiry timestamp"""

    def test_stores_value_with_timestamp(self):
        cache = DiscordCache(ttl=300)
        before = time.time()
        cache.set('key', 'value')
        after = time.time()

        expiry, data = cache.cache['key']
        assert data == 'value'
        assert before + 300 <= expiry <= after + 300

    def test_overwrites_existing_key(self):
        cache = DiscordCache(ttl=300)
        cache.set('key', 'first')
        cache.set('key', 'second')
        assert cache.get('key') == 'second'


class TestDiscordCacheClear:
    """unit: DiscordCache.clear() removes entries"""

    def test_clear_all(self):
        cache = DiscordCache(ttl=300)
        cache.set('a', 1)
        cache.set('b', 2)
        cache.clear()
        assert len(cache.cache) == 0

    def test_clear_with_prefix(self):
        cache = DiscordCache(ttl=300)
        cache.set('channels:123', [1, 2])
        cache.set('channels:456', [3, 4])
        cache.set('roles:123', [5])
        cache.clear(prefix='channels:')
        assert 'channels:123' not in cache.cache
        assert 'channels:456' not in cache.cache
        assert cache.get('roles:123') == [5]

    def test_clear_prefix_no_match(self):
        cache = DiscordCache(ttl=300)
        cache.set('roles:123', [1])
        cache.clear(prefix='channels:')
        assert cache.get('roles:123') == [1]


# ============================================================
# fixtures / helpers
# ============================================================


@pytest.fixture(autouse=True)
def _clear_module_cache():
    """clear the module-level cache before each test to prevent cross-test contamination"""
    _cache.clear()
    yield
    _cache.clear()


def _make_text_channel(*, id_, name, position=0, category_id=None):
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = id_
    ch.name = name
    ch.position = position
    ch.category_id = category_id
    ch.type = MagicMock()
    ch.type.name = 'text'
    return ch


def _make_voice_channel(*, id_, name, position=0, category_id=None):
    ch = MagicMock(spec=discord.VoiceChannel)
    ch.id = id_
    ch.name = name
    ch.position = position
    ch.category_id = category_id
    ch.type = MagicMock()
    ch.type.name = 'voice'
    return ch


def _make_thread(*, id_, name, parent_id, thread_type='public_thread'):
    t = MagicMock(spec=discord.Thread)
    t.id = id_
    t.name = name
    t.parent_id = parent_id
    t.type = MagicMock()
    t.type.name = thread_type
    return t


def _make_role(*, id_, name, position, color_value=0, managed=False, is_default=False):
    r = MagicMock()
    r.id = id_
    r.name = name
    r.position = position
    r.color = MagicMock()
    r.color.value = color_value
    r.managed = managed
    r.is_default = MagicMock(return_value=is_default)
    return r


def _make_user(*, id_, name, global_name='TestUser', avatar_url='https://cdn.example.com/avatar.png'):
    u = MagicMock()
    u.id = id_
    u.name = name
    u.global_name = global_name
    u.avatar = True  # truthy so avatar_url branch is taken
    u.display_avatar = MagicMock()
    u.display_avatar.url = avatar_url
    return u


def _make_guild(*, id_, name, icon_url='https://cdn.example.com/icon.png'):
    g = MagicMock()
    g.id = id_
    g.name = name
    g.icon = MagicMock()
    g.icon.url = icon_url
    return g


# ============================================================
# get_guild_channels()
# ============================================================


class TestGetGuildChannels:
    """unit: get_guild_channels fetches and formats channels via pycord"""

    async def test_returns_channels_and_threads(self):
        text_ch = _make_text_channel(id_=100, name='general', position=0)
        voice_ch = _make_voice_channel(id_=200, name='voice-chat', position=1)
        thread = _make_thread(id_=300, name='discussion', parent_id=100)

        mock_guild = AsyncMock()
        mock_guild.fetch_channels = AsyncMock(return_value=[text_ch, voice_ch])
        mock_guild.active_threads = AsyncMock(return_value=[thread])

        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(return_value=mock_guild)
            result = await get_guild_channels(999)

        assert result is not None
        assert len(result) == 3

        # channels sorted by position, then threads appended
        assert result[0]['name'] == 'general'
        assert result[0]['is_thread'] is False
        assert result[1]['name'] == 'voice-chat'
        assert result[2]['name'] == 'discussion'
        assert result[2]['is_thread'] is True
        assert result[2]['parent_id'] == '100'

    async def test_guild_not_found_returns_none(self):
        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))
            result = await get_guild_channels(999)

        assert result is None

    async def test_uses_cache_on_second_call(self):
        text_ch = _make_text_channel(id_=100, name='general', position=0)

        mock_guild = AsyncMock()
        mock_guild.fetch_channels = AsyncMock(return_value=[text_ch])
        mock_guild.active_threads = AsyncMock(return_value=[])

        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(return_value=mock_guild)
            first = await get_guild_channels(888)
            second = await get_guild_channels(888)

        assert first == second
        # fetch_guild should only be called once (second call uses cache)
        mock_bot.fetch_guild.assert_awaited_once()


# ============================================================
# get_guild_roles()
# ============================================================


class TestGetGuildRoles:
    """unit: get_guild_roles fetches and formats roles via pycord"""

    async def test_returns_roles_sorted_by_position_descending(self):
        role_admin = _make_role(id_=10, name='Admin', position=3, color_value=0xFF0000)
        role_mod = _make_role(id_=20, name='Mod', position=2)
        role_default = _make_role(id_=30, name='@everyone', position=0, is_default=True)

        mock_guild = AsyncMock()
        mock_guild.fetch_roles = AsyncMock(return_value=[role_admin, role_mod, role_default])

        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(return_value=mock_guild)
            result = await get_guild_roles(999)

        assert len(result) == 3
        # descending by position
        assert result[0]['name'] == 'Admin'
        assert result[0]['position'] == 3
        assert result[0]['color'] == hex(0xFF0000)
        assert result[2]['is_default'] is True

    async def test_guild_not_found_returns_empty_list(self):
        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))
            result = await get_guild_roles(999)

        assert result == []


# ============================================================
# get_user_info()
# ============================================================


class TestGetUserInfo:
    """unit: get_user_info fetches and formats user data via pycord"""

    async def test_user_found(self):
        mock_user = _make_user(id_=42, name='johndoe', global_name='John Doe')

        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_user = AsyncMock(return_value=mock_user)
            result = await get_user_info(42)

        assert result is not None
        assert result['id'] == '42'
        assert result['name'] == 'johndoe'
        assert result['global_name'] == 'John Doe'
        assert result['avatar_url'] == 'https://cdn.example.com/avatar.png'

    async def test_user_not_found(self):
        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_user = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))
            result = await get_user_info(42)

        assert result is None

    async def test_user_without_avatar(self):
        mock_user = _make_user(id_=42, name='noavatar')
        mock_user.avatar = None  # no custom avatar

        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_user = AsyncMock(return_value=mock_user)
            result = await get_user_info(42)

        assert result is not None
        assert result['avatar_url'] is None


# ============================================================
# get_guild_info()
# ============================================================


class TestGetGuildInfo:
    """unit: get_guild_info fetches and formats guild data via pycord"""

    async def test_guild_found(self):
        mock_guild = _make_guild(id_=999, name='Test Server')

        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(return_value=mock_guild)
            result = await get_guild_info(999)

        assert result is not None
        assert result['id'] == '999'
        assert result['name'] == 'Test Server'
        assert result['icon_url'] == 'https://cdn.example.com/icon.png'

    async def test_guild_not_found(self):
        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))
            result = await get_guild_info(999)

        assert result is None

    async def test_guild_without_icon(self):
        mock_guild = _make_guild(id_=999, name='No Icon')
        mock_guild.icon = None

        with patch('doom_bot.web.discord_integration.bot') as mock_bot:
            mock_bot.fetch_guild = AsyncMock(return_value=mock_guild)
            result = await get_guild_info(999)

        assert result is not None
        assert result['icon_url'] is None


# ============================================================
# invalidate_guild_cache()
# ============================================================


class TestInvalidateGuildCache:
    """unit: invalidate_guild_cache clears cache entries for a specific guild"""

    def test_clears_channels_roles_and_guild_info(self):
        _cache.set('channels:123', [1, 2])
        _cache.set('roles:123', [3, 4])
        _cache.set('guild_info:123', {'name': 'test'})
        _cache.set('channels:456', [5, 6])  # different guild, should survive

        invalidate_guild_cache(123)

        assert _cache.get('channels:123') is None
        assert _cache.get('roles:123') is None
        assert _cache.get('guild_info:123') is None
        assert _cache.get('channels:456') == [5, 6]

    def test_no_error_when_cache_empty(self):
        # should not raise even with nothing cached
        invalidate_guild_cache(999)

    def test_does_not_affect_user_cache(self):
        _cache.set('user:42', {'name': 'testuser'})
        invalidate_guild_cache(42)
        assert _cache.get('user:42') == {'name': 'testuser'}
