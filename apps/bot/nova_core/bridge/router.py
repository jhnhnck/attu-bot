# SPDX-License-Identifier: Apache-2.0
"""nova_core.bridge.router | bridge endpoints + uvicorn task launcher."""

import asyncio
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from nova_core import __config_version__, __schema__
from nova_core.bridge import discord_integration as di
from nova_core.bridge.hmac import verify
from nova_core.client.core import bot, config


logger = structlog.stdlib.get_logger(__name__)


# --- request models ---


class CacheInvalidateRequest(BaseModel):
    guild_id: int


class ReloadRequest(BaseModel):
    signal_type: Literal['guild', 'theme', 'system']
    guild_id: int | None = None


class UserLookupRequest(BaseModel):
    user_ids: list[int]


# --- routers ---

# signed: every endpoint here requires a valid x-bridge-signature
signed = APIRouter(prefix='/bridge', dependencies=[Depends(verify)])

# unsigned: only /bridge/health, used by compose healthcheck
unsigned = APIRouter(prefix='/bridge')


@unsigned.get('/health')
async def health() -> dict[str, Any]:
    """liveness probe; reports schema versions for compose's healthcheck-gated server boot."""
    return {
        'status': 'ok',
        'schema': __schema__,
        'config_version': __config_version__,
        'bot_ready': getattr(bot, '_bot_initialized', False),
    }


@signed.get('/guilds/{guild_id}/channels')
async def get_channels(guild_id: int) -> dict[str, Any]:
    result = await di.get_guild_channels(guild_id)
    if result is None:
        raise HTTPException(status_code=502, detail='discord channel lookup failed')
    return {'channels': result}


@signed.get('/guilds/{guild_id}/roles')
async def get_roles(guild_id: int) -> dict[str, Any]:
    result = await di.get_guild_roles(guild_id)
    if result is None:
        raise HTTPException(status_code=502, detail='discord role lookup failed')
    return {'roles': result}


@signed.get('/guilds/{guild_id}/info')
async def get_info(guild_id: int) -> dict[str, Any]:
    result = await di.get_guild_info(guild_id)
    if result is None:
        raise HTTPException(status_code=502, detail='discord guild info lookup failed')
    return result


@signed.get('/users/{user_id}')
async def get_user(user_id: int) -> dict[str, Any]:
    result = await di.get_user_info(user_id)
    if result is None:
        raise HTTPException(status_code=502, detail='discord user lookup failed')
    return result


@signed.post('/users/lookup')
async def lookup_users(req: UserLookupRequest) -> dict[str, Any]:
    return {'users': await di.get_users_info(req.user_ids)}


@signed.post('/cache/invalidate')
async def invalidate_cache(req: CacheInvalidateRequest) -> dict[str, Any]:
    di.invalidate_guild_cache(req.guild_id)
    return {'success': True}


@signed.post('/reload')
async def reload_config(req: ReloadRequest) -> dict[str, Any]:
    """mirror the reload_watcher.py behavior; called synchronously from the server."""
    if req.signal_type == 'guild':
        if req.guild_id is None:
            raise HTTPException(status_code=400, detail='guild_id required for guild reload')
        logger.info(f'reloading guild config for {req.guild_id} (bridge-triggered)')
        success = await config.load_guild(req.guild_id)
        if not success:
            raise HTTPException(status_code=500, detail='guild reload failed validation')

    elif req.signal_type == 'theme':
        logger.info('reloading theme config (bridge-triggered)')
        success = await config.load_theme()
        if not success:
            raise HTTPException(status_code=500, detail='theme reload failed validation')

        # local imports avoid circular dependency with tasks/__init__.py; matches the existing reload_watcher pattern
        from nova_core.tasks.logo_update import logo_update_task
        from nova_core.tasks.scheduler import scheduler

        scheduler.add_job(logo_update_task.run(), 'LogoUpdate', 'immediate')
        logger.info('triggered immediate logo update from theme reload')

    elif req.signal_type == 'system':
        logger.info('reloading system globals (bridge-triggered)')
        await config.load_globals()

    return {'success': True, 'signal_type': req.signal_type}


# --- ops: request models ---


class BackfillChannelRequest(BaseModel):
    guild_id: int
    channel_id: int


class BackfillGuildRequest(BaseModel):
    guild_id: int
    lookback_days: int = 1


class GuildIdRequest(BaseModel):
    guild_id: int


class CcboardPurgeRequest(BaseModel):
    guild_id: int
    message_id: int


class CcboardRecoverRequest(BaseModel):
    guild_id: int
    dry_run: bool = True


class CcboardCleanupRequest(BaseModel):
    guild_id: int
    dry_run: bool = True


class CcboardRecountRequest(BaseModel):
    guild_id: int
    message_id: int | None = None
    dry_run: bool = True


class TriggerYearLinksRequest(BaseModel):
    guild_id: int


# --- ops: backfill ---


@signed.post('/bridge/ops/backfill/channel')
async def ops_backfill_channel(req: BackfillChannelRequest) -> dict[str, Any]:
    from nova_core.commands.fix import job_backfill_channel
    from nova_core.tasks import scheduler

    scheduler.add_job(job_backfill_channel(req.channel_id, req.guild_id), 'Job', 'backfill_channel', req.channel_id)
    logger.info(f'ops: scheduled backfill_channel ch={req.channel_id} guild={req.guild_id}')
    return {'scheduled': True, 'channel_id': req.channel_id}


@signed.post('/bridge/ops/backfill/guild')
async def ops_backfill_guild(req: BackfillGuildRequest) -> dict[str, Any]:
    from datetime import timedelta

    from nova_core.commands.fix import job_reconcile_guild
    from nova_core.tasks import scheduler

    lookback = timedelta(days=req.lookback_days) if req.lookback_days > 0 else None
    scheduler.add_job(job_reconcile_guild(req.guild_id, lookback=lookback), 'Job', 'backfill_guild')
    logger.info(f'ops: scheduled backfill_guild guild={req.guild_id} lookback_days={req.lookback_days}')
    return {'scheduled': True}


# --- ops: ccboard ---


@signed.post('/bridge/ops/ccboard/regen')
async def ops_ccboard_regen(req: GuildIdRequest) -> dict[str, Any]:
    from nova_core import ccboard

    if ccboard._entry_repo is None:
        raise HTTPException(status_code=503, detail='ccboard entry repo not initialized')
    affected = await ccboard._entry_repo.mark_all_dirty(req.guild_id)
    logger.info(f'ops: ccboard_regen guild={req.guild_id} affected={affected}')
    return {'affected': affected}


@signed.post('/bridge/ops/ccboard/purge')
async def ops_ccboard_purge(req: CcboardPurgeRequest) -> dict[str, Any]:
    import time

    from nova_core import ccboard

    if ccboard._entry_repo is None or ccboard._reaction_repo is None:
        raise HTTPException(status_code=503, detail='ccboard repos not initialized')

    entry = await ccboard._entry_repo.get(req.message_id)
    if entry is None:
        entry = await ccboard._entry_repo.get_by_starboard_message(req.message_id)
    if entry is None:
        entry = await ccboard._entry_repo.get_by_display_message(req.message_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f'no ccboard entry for {req.message_id}')

    deleted_post = False
    if entry.starboard_message_id:
        try:
            guild_cfg = config.guild(req.guild_id)
            cc_channel = bot.get_channel(guild_cfg.ccboard.channel_id)
            if cc_channel:
                await cc_channel.get_partial_message(entry.starboard_message_id).delete()
                deleted_post = True
        except Exception as err:
            logger.warning(f'ops ccboard_purge: could not delete post {entry.starboard_message_id}: {err}')

    now = int(time.time())
    await ccboard._reaction_repo.soft_delete_all_for_message(entry.message_id, now=now)
    await ccboard._entry_repo.delete(entry.message_id)

    logger.info(f'ops: ccboard_purge msg={entry.message_id} guild={req.guild_id} deleted_post={deleted_post}')
    return {'purged': True, 'message_id': entry.message_id, 'deleted_post': deleted_post}


@signed.post('/bridge/ops/ccboard/recover')
async def ops_ccboard_recover(req: CcboardRecoverRequest) -> dict[str, Any]:
    from nova_core.ccboard.auditor import auditor_task

    result = await auditor_task.discover_guild(req.guild_id, dry_run=req.dry_run)
    return {'summary': result.summary, 'mutated': result.mutated, 'dry_run': result.dry_run, 'details': result.details}


@signed.post('/bridge/ops/ccboard/cleanup')
async def ops_ccboard_cleanup(req: CcboardCleanupRequest) -> dict[str, Any]:
    from nova_core.ccboard.auditor import auditor_task

    result = await auditor_task.cleanup_orphans(req.guild_id, dry_run=req.dry_run)
    return {'summary': result.summary, 'mutated': result.mutated, 'dry_run': result.dry_run, 'details': result.details}


@signed.post('/bridge/ops/ccboard/recount')
async def ops_ccboard_recount(req: CcboardRecountRequest) -> dict[str, Any]:
    from nova_core.ccboard.auditor import auditor_task

    if req.message_id is not None:
        result = await auditor_task.reconcile_entry(req.guild_id, req.message_id, dry_run=req.dry_run)
    else:
        result = await auditor_task.reconcile_guild(req.guild_id, dry_run=req.dry_run)
    return {'summary': result.summary, 'mutated': result.mutated, 'dry_run': result.dry_run, 'details': result.details}


@signed.get('/bridge/ops/ccboard/reactions')
async def ops_ccboard_reactions(guild_id: int, message_id: int) -> dict[str, Any]:
    from nova_core import ccboard

    if ccboard._entry_repo is None or ccboard._reaction_repo is None:
        raise HTTPException(status_code=503, detail='ccboard repos not initialized')

    entry = await ccboard._entry_repo.get(message_id)
    if entry is None:
        entry = await ccboard._entry_repo.get_by_starboard_message(message_id)
    if entry is None:
        entry = await ccboard._entry_repo.get_by_display_message(message_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f'no ccboard entry for {message_id}')

    reactions = await ccboard._reaction_repo.list_for_message(entry.message_id, include_removed=True)
    rows = [
        {
            'user_id': str(r.user_id),
            'emoji_str': r.emoji_str,
            'point_value': r.point_value,
            'is_super': r.is_super,
            'removed': r.removed,
            'reacted_at': r.reacted_at,
            'removed_at': r.removed_at,
            'last_recounted_at': r.last_recounted_at,
        }
        for r in reactions
    ]
    return {'message_id': str(entry.message_id), 'reactions': rows}


# --- ops: triggers ---


@signed.post('/bridge/ops/trigger/logo')
async def ops_trigger_logo() -> dict[str, Any]:
    from nova_core.tasks.logo_update import logo_update_task
    from nova_core.tasks.scheduler import scheduler

    scheduler.add_job(logo_update_task.run(), 'LogoUpdate', 'immediate')
    logger.info('ops: scheduled logo update')
    return {'scheduled': True}


@signed.post('/bridge/ops/trigger/year-links')
async def ops_trigger_year_links(req: TriggerYearLinksRequest) -> dict[str, Any]:
    from nova_core.tasks import scheduler
    from nova_core.tasks.nova_year import job_construct_year_links

    scheduler.add_job(job_construct_year_links(req.guild_id), 'Job', 'construct_year_links')
    logger.info(f'ops: scheduled year_links guild={req.guild_id}')
    return {'scheduled': True}


@signed.post('/bridge/ops/trigger/emoji-sync')
async def ops_trigger_emoji_sync() -> dict[str, Any]:
    import asyncio

    from nova_core.eggs.emojis import ensure_egg_emojis, ensure_progress_emojis

    secondary = config.get_guild_by_role('secondary')
    guild = bot.get_guild(secondary.id) if secondary is not None else None
    if guild is None:
        raise HTTPException(status_code=404, detail='secondary guild not in cache')

    egg_emojis, progress_emojis = await asyncio.gather(
        ensure_egg_emojis(guild),
        ensure_progress_emojis(guild),
    )
    config.theme.egg_emojis = {rarity: e.id for rarity, e in egg_emojis.items()}
    config.theme.progress_emojis = {segment: e.id for segment, e in progress_emojis.items()}
    await config.theme.save()

    logger.info(f'ops: emoji_sync done egg={len(egg_emojis)} progress={len(progress_emojis)}')
    return {'egg_emojis': list(egg_emojis.keys()), 'progress_emojis': list(progress_emojis.keys())}


# --- ops: info ---


@signed.get('/bridge/ops/info/version')
async def ops_info_version() -> dict[str, Any]:
    from platform import freedesktop_os_release as os_release
    from platform import python_version

    from nova_core import __build_time__, __schema__, __title__, __version__

    distro_info = os_release()
    return {
        'title': __title__,
        'version': __version__,
        'schema': __schema__,
        'build_time': __build_time__,
        'python': python_version(),
        'distro': f'{distro_info["ID"].capitalize()} {distro_info["VERSION_ID"]}',
    }


@signed.get('/bridge/ops/info/year-stats')
async def ops_info_year_stats(guild_id: int) -> dict[str, Any]:
    from nova_core.client.calendar import get_year_span, get_year_status

    elapsed_days, current_year = get_year_status(guild=guild_id)
    year_span = await get_year_span(current_year, guild=guild_id)
    guild_cfg = config.guild(guild_id)
    return {
        'current_year': current_year,
        'elapsed_days': elapsed_days,
        'epoch_time': guild_cfg.epoch.time,
        'epoch_year': guild_cfg.epoch.year,
        'year_span_start': year_span.start_time,
        'year_span_end': year_span.end_time,
        'year_span_duration': year_span.duration,
    }


@signed.get('/bridge/ops/info/epoch')
async def ops_info_epoch(guild_id: int) -> dict[str, Any]:
    guild_cfg = config.guild(guild_id)
    epoch = guild_cfg.epoch
    return {
        'time': epoch.time,
        'year': epoch.year,
        'length': epoch.length,
        'paused': epoch.paused,
        'rollover_minutes': epoch.rollover_minutes,
    }


@signed.get('/bridge/ops/info/scheduler')
async def ops_info_scheduler() -> dict[str, Any]:
    from nova_core.tasks import scheduler

    return {'running': list(scheduler.running_tasks), 'count': scheduler.count}


# --- ops: inspect ---


@signed.get('/bridge/ops/inspect/message')
async def ops_inspect_message(guild_id: int, channel_id: int, message_id: int) -> dict[str, Any]:
    from discord.utils import snowflake_time

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception as err:
            raise HTTPException(status_code=404, detail=f'channel {channel_id} not found: {err}') from err

    message = None
    try:
        async for msg in channel.history(around=snowflake_time(message_id), limit=15):
            if msg.id == message_id:
                message = msg
                break
    except Exception as err:
        raise HTTPException(status_code=404, detail=f'could not read message history: {err}') from err

    if message is None:
        raise HTTPException(status_code=404, detail=f'message {message_id} not found in channel history')

    return {
        'id': str(message.id),
        'author': {'id': str(message.author.id), 'name': str(message.author)},
        'channel_id': str(channel_id),
        'guild_id': str(guild_id),
        'timestamp': message.created_at.isoformat(),
        'edited_at': message.edited_at.isoformat() if message.edited_at else None,
        'pinned': message.pinned,
        'content': message.content,
        'embeds': [e.to_dict() for e in message.embeds],
        'attachments': [{'id': str(a.id), 'filename': a.filename, 'url': a.url} for a in message.attachments],
        'reactions': [{'emoji': str(r.emoji), 'count': r.count} for r in message.reactions],
    }


# --- app builder + task launcher ---


def build_app() -> FastAPI:
    """assemble the fastapi app; exposed for tests + e2e signed-curl scripts."""
    app = FastAPI(title='nova bridge', docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(unsigned)
    app.include_router(signed)
    return app


def start_bridge_task() -> None:
    """schedule the bridge uvicorn server on the bot's event loop after on_ready.

    using bot.loop avoids a second event loop and lets bridge handlers await
    pycord coroutines (fetch_guild, fetch_user) directly.
    """
    import uvicorn  # lazy: uvicorn is not present in unit/component test containers

    if getattr(bot, '_bridge_started', False):
        return

    app = build_app()
    server_config = uvicorn.Config(
        app,
        host=config.bridge.bind_host,
        port=config.bridge.bot_port,
        log_config=None,
        access_log=False,
        lifespan='off',
    )
    server = uvicorn.Server(server_config)

    async def _serve() -> None:
        logger.info(f'starting bridge on {config.bridge.bind_host}:{config.bridge.bot_port}')
        try:
            await server.serve()
            bot._bridge_started = True
        except asyncio.CancelledError:
            logger.info('bridge cancelled; shutting down')
            raise
        except Exception as e:
            logger.error(f'bridge server crashed: {e!s}')
            bot._bridge_started = False

    bot.loop.create_task(_serve())
