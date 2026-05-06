"""
AttuBot - Web Helpers
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import time

from attubot.client.core import config, db
from attubot.logging import get_logger


logger = get_logger(__name__)


async def get_admin_stats_data() -> dict:
    """gather system stats and data counts for the dashboard."""
    from attubot.client.markers import YearMarker
    from attubot.client.years import Year

    total_guilds = len(config.authorized_guilds)
    configured_guilds = len(config.valid_guilds)

    total_years = 0
    total_markers = 0
    total_starred_messages = 0
    total_stars = 0

    try:
        from attubot.client.starboard import _get_repo as _get_sb_repo

        sb_repo = _get_sb_repo()
        for gid in config.authorized_guilds:
            total_years += await Year.total(gid)
            total_markers += await YearMarker.total(gid)
            total_starred_messages += await sb_repo.total_for_guild(gid)
            total_stars += await sb_repo.sum_reactions_for_guild(gid)
    except RuntimeError:
        for gid in config.authorized_guilds:
            total_years += await Year.total(gid)
            total_markers += await YearMarker.total(gid)

    total_eggs_hatched = 0
    try:
        from attubot.eggs.hatching import _egg_repo as egg_repo

        if egg_repo is not None:
            total_eggs_hatched = await egg_repo.count_hatched()
    except Exception as e:
        logger.debug(f'egg stats unavailable: {e}')

    try:
        db_connected = db.get_db() is not None
    except Exception:
        db_connected = False

    config_loaded = config._get_event('load').is_set()
    uptime_seconds = int(time.time() - config._init_time) if hasattr(config, '_init_time') else 0

    return {
        'guilds': {
            'total': total_guilds,
            'configured': configured_guilds,
            'authorized': list(str(g) for g in config.authorized_guilds),
        },
        'data': {
            'total_years': total_years,
            'total_markers': total_markers,
            'total_starred_messages': total_starred_messages,
            'total_stars': total_stars,
            'total_eggs_hatched': total_eggs_hatched,
        },
        'system': {
            'db_connected': db_connected,
            'config_loaded': config_loaded,
            'uptime_seconds': uptime_seconds,
            'primary_guild': str(config.primary_guild),
            'config_version': config.config_version,
        },
    }


async def get_time_status_data(guild_id: int) -> dict:
    """gather time status for a guild."""
    from attubot.client.calendar import get_next_year, get_year_status

    guild_config = config.guilds.get(guild_id)
    if not guild_config:
        return {}

    elapsed_days, current_year = get_year_status(guild_id)
    next_rollover = get_next_year(guild_id)

    rollover_time = guild_config.epoch.get_rollover_time()
    rollover_str = rollover_time.strftime('%H:%M')

    return {
        'guild_id': str(guild_id),
        'current_year': current_year,
        'elapsed_days': elapsed_days,
        'current_day': (elapsed_days % guild_config.epoch.length) + 1,
        'next_rollover': int(next_rollover.timestamp()),
        'next_rollover_formatted': next_rollover.strftime('%Y-%m-%d %H:%M:%S %Z'),
        'paused': guild_config.epoch.paused,
        'year_length': guild_config.epoch.length,
        'rollover_time': rollover_str,
        'rollover_minutes': guild_config.epoch.rollover_minutes,
        'epoch_time': guild_config.epoch.time,
        'epoch_year': guild_config.epoch.year,
    }


async def get_recent_audit_data(guild_id: int | None = None, limit: int = 5) -> list[dict]:
    """fetch recent audit log entries with haracalnde dates."""
    from datetime import datetime

    from attubot.web import app as web_app

    if not web_app.audit_logger:
        return []

    try:
        logs = await web_app.audit_logger.get_logs(limit=limit, skip=0, guild_id=guild_id)

        for log in logs:
            if '_id' in log:
                log['_id'] = str(log['_id'])
            if 'guild_id' in log and log['guild_id'] is not None:
                log['guild_id'] = str(log['guild_id'])
            log['timestamp_formatted'] = datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %H:%M:%S')

            # add haracalnde date
            try:
                from attubot.client.calendar import haracalnde_date

                log['haracalnde'] = await haracalnde_date(int(log['timestamp']), guild_id)
            except Exception:
                log['haracalnde'] = ''

        return logs
    except Exception as e:
        logger.error(f'error fetching audit logs: {e}')
        return []


async def get_guild_config_data(guild_id: int) -> dict:
    """assemble guild config with discord name resolution for SSR.

    Returns the same shape as GET /api/guilds/<id> so the frontend can
    consume it identically whether it comes from SSR or API.
    """
    from attubot.web.discord_integration import get_guild_channels, get_guild_roles, get_users_info

    guild = config.guilds.get(guild_id)
    if not guild:
        return {}

    rollover_time = guild.epoch.get_rollover_time()
    rollover_str = rollover_time.strftime('%H:%M')

    all_channels = await get_guild_channels(guild_id)
    all_roles = await get_guild_roles(guild_id)
    channel_map = {ch['id']: ch['name'] for ch in (all_channels or [])}

    marker_user_ids = [int(uid) for uid in guild.users.markers if uid]
    valid_bot_ids = [int(b) for b in guild.starboard.valid_bots if b]
    all_user_ids = list(set(marker_user_ids + valid_bot_ids))
    users_info = await get_users_info(all_user_ids) if all_user_ids else []
    user_map = {u['id']: u.get('global_name') or u.get('name', 'Unknown') for u in users_info}

    def ch_name(cid):
        return channel_map.get(str(cid)) if cid else None

    def u_name(uid):
        return user_map.get(str(uid)) if uid else None

    return {
        'config': {
            'guild_id': str(guild.id),
            'name': str(guild),
            'channels': {
                'activity': str(guild.channels.activity) if guild.channels.activity else '0',
                'activity_name': ch_name(guild.channels.activity),
                'announcements': str(guild.channels.announcements) if guild.channels.announcements else '0',
                'announcements_name': ch_name(guild.channels.announcements),
                'year_vc': str(guild.channels.year_vc) if guild.channels.year_vc else '0',
                'year_vc_name': ch_name(guild.channels.year_vc),
                'year_links': str(guild.channels.year_links) if guild.channels.year_links else '0',
                'year_links_name': ch_name(guild.channels.year_links),
                'meta_chat': str(guild.channels.meta_chat) if guild.channels.meta_chat else '0',
                'meta_chat_name': ch_name(guild.channels.meta_chat),
                'general': str(guild.channels.general) if guild.channels.general else '0',
                'general_name': ch_name(guild.channels.general),
                'logs': str(guild.channels.logs) if guild.channels.logs else '0',
                'logs_name': ch_name(guild.channels.logs),
                'eggs': str(guild.channels.eggs) if guild.channels.eggs else '0',
                'eggs_name': ch_name(guild.channels.eggs),
                'lore_channels': [str(ch) for ch in guild.channels.lore_channels],
                'lore_channels_names': [ch_name(ch) for ch in guild.channels.lore_channels],
                'canon_channels': [str(ch) for ch in guild.channels.canon_channels],
                'canon_channels_names': [ch_name(ch) for ch in guild.channels.canon_channels],
            },
            'epoch': {
                'time': guild.epoch.time,
                'year': guild.epoch.year,
                'length': guild.epoch.length,
                'paused': guild.epoch.paused,
                'rollover_minutes': guild.epoch.rollover_minutes,
                'rollover_time': rollover_str,
            },
            'roles': {
                'announcements': str(guild.roles.announcements) if guild.roles.announcements else '0',
                'bot_color': str(guild.roles.bot_color) if guild.roles.bot_color else '0',
                'trees_admin_role': str(guild.roles.trees_admin_role) if guild.roles.trees_admin_role else '0',
                'trees_user_role': str(guild.roles.trees_user_role) if guild.roles.trees_user_role else '0',
            },
            'users': {
                'markers': [str(u) for u in guild.users.markers],
                'markers_names': [u_name(u) for u in guild.users.markers],
            },
            'starboard': {
                'channel_id': str(guild.starboard.channel_id) if guild.starboard.channel_id else '0',
                'channel_id_name': ch_name(guild.starboard.channel_id),
                'emojis': guild.starboard.emojis,
                'valid_bots': [str(b) for b in guild.starboard.valid_bots],
                'valid_bots_names': [u_name(b) for b in guild.starboard.valid_bots],
            },
        },
        'channels': all_channels or [],
        'roles': all_roles or [],
    }


def format_uptime(seconds: int) -> str:
    """format uptime seconds into a human-readable string."""
    if not seconds or seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m'
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h < 24:
        return f'{h}h {m}m'
    d = h // 24
    return f'{d}d {h % 24}h'
