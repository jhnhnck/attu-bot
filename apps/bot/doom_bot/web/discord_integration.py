# SPDX-License-Identifier: Apache-2.0
"""doom_bot.web.discord_integration | discord API integration using pycord."""

import time
from typing import Any

import discord

from doom_bot import bot
from doom_bot.logging import get_logger


logger = get_logger(__name__)


class DiscordCache:
    """Simple in-memory cache for Discord API results"""

    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self.cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if key in self.cache:
            expiry, data = self.cache[key]
            if time.time() < expiry:
                return data
            del self.cache[key]
        return None

    def set(self, key: str, data: Any):
        self.cache[key] = (time.time() + self.ttl, data)

    def clear(self, prefix: str | None = None):
        if prefix:
            keys_to_delete = [k for k in self.cache if k.startswith(prefix)]
            for k in keys_to_delete:
                del self.cache[k]
        else:
            self.cache.clear()


# Global cache instance
_cache = DiscordCache()


async def get_guild_channels(guild_id: int) -> list[dict[str, Any]] | None:
    """Fetch all channels for a guild using Pycord, including threads"""
    cache_key = f'channels:{guild_id}'
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        guild = await bot.fetch_guild(guild_id)
        channels = await guild.fetch_channels()
        threads = await guild.active_threads()

        result = []
        threads_result = []

        for c in [*channels, *threads]:
            # We only care about text, voice, and category channels for config
            if isinstance(c, discord.TextChannel | discord.VoiceChannel | discord.CategoryChannel | discord.StageChannel | discord.ForumChannel):
                result.append({
                    'id': str(c.id),
                    'name': c.name,
                    'type': c.type.name if hasattr(c.type, 'name') else str(c.type),
                    'position': c.position,
                    'category_id': str(c.category_id) if hasattr(c, 'category_id') and c.category_id else None,
                    'is_thread': False,
                })
            # Handle thread types (public threads, private threads, announcement threads)
            elif isinstance(c, discord.Thread):
                parent_channel = next((ch for ch in channels if hasattr(ch, 'id') and str(ch.id) == str(c.parent_id)), None)
                parent_name = parent_channel.name if parent_channel else 'Unknown'
                thread_type = c.type.name if hasattr(c.type, 'name') else str(c.type)
                threads_result.append({
                    'id': str(c.id),
                    'name': c.name,
                    'type': thread_type,
                    'position': None,
                    'category_id': None,
                    'parent_id': str(c.parent_id) if c.parent_id else None,
                    'parent_name': parent_name,
                    'is_thread': True,
                })

        # Sort channels by position
        result.sort(key=lambda x: x['position'])

        # Sort threads by position and append to result
        threads_result.sort(key=lambda x: x['name'])
        result.extend(threads_result)

        _cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f'failed to fetch channels for guild {guild_id} via pycord: {e}')
        return None


async def get_guild_roles(guild_id: int) -> list[dict[str, Any]]:
    """Fetch all roles for a guild using Pycord"""
    cache_key = f'roles:{guild_id}'
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        guild = await bot.fetch_guild(guild_id)
        roles = await guild.fetch_roles()

        result = [
            {
                'id': str(r.id),
                'name': r.name,
                'color': hex(r.color.value),
                'position': r.position,
                'managed': r.managed,
                'is_default': r.is_default(),
            }
            for r in roles
        ]

        # Sort by position (descending, like Discord UI)
        result.sort(key=lambda x: x['position'], reverse=True)

        _cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f'failed to fetch roles for guild {guild_id} via pycord: {e}')
        return []


async def get_user_info(user_id: int) -> dict[str, Any] | None:
    """Fetch user information using Pycord"""
    cache_key = f'user:{user_id}'
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        user = await bot.fetch_user(user_id)
        result = {
            'id': str(user.id),
            'name': user.name,
            'global_name': user.global_name,
            'avatar_url': user.display_avatar.url if user.avatar else None,
        }
        _cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f'failed to fetch user {user_id} via pycord: {e}')
        return None


async def get_guild_info(guild_id: int) -> dict[str, Any] | None:
    """Fetch guild information using Pycord"""
    cache_key = f'guild_info:{guild_id}'
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        guild = await bot.fetch_guild(guild_id)
        result = {
            'id': str(guild.id),
            'name': guild.name,
            'icon_url': guild.icon.url if guild.icon else None,
        }
        _cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f'failed to fetch guild {guild_id} via pycord: {e}')
        return None


async def get_users_info(user_ids: list[int]) -> list[dict[str, Any]]:
    """Fetch user information for multiple user IDs"""
    result = []
    for user_id in user_ids:
        user_info = await get_user_info(user_id)
        if user_info:
            result.append(user_info)
    return result


def invalidate_guild_cache(guild_id: int):
    """Invalidate cache for a specific guild"""
    _cache.clear(prefix=f'channels:{guild_id}')
    _cache.clear(prefix=f'roles:{guild_id}')
    _cache.clear(prefix=f'guild_info:{guild_id}')
