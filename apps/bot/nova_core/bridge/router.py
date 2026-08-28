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
        host='0.0.0.0',  # noqa: S104 - exposure is controlled by compose (no published port), not the bind address
        port=config.bridge.bot_port,
        log_config=None,
        access_log=False,
        lifespan='off',
    )
    server = uvicorn.Server(server_config)

    async def _serve() -> None:
        logger.info(f'starting bridge on 0.0.0.0:{config.bridge.bot_port}')
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
