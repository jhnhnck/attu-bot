# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.ops | forwarding routes for bot operational commands."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from attu_server.api.admin.guilds import _build_guild_slug_map
from attu_server.api.admin.slugs import resolve_guild_id
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig
from attu_server.deps import get_bridge, get_config


router = APIRouter()

# auditor passes run up to 90s; add margin for bridge latency
_LONG_TIMEOUT = 120.0


# --- request bodies ---


class BackfillChannelBody(BaseModel):
    channel_id: int


class BackfillGuildBody(BaseModel):
    lookback_days: int = 1


class CcboardPurgeBody(BaseModel):
    message_id: int


class CcboardDryRunBody(BaseModel):
    dry_run: bool = True


class CcboardRecountBody(BaseModel):
    message_id: int | None = None
    dry_run: bool = True


# --- helpers ---


async def _resolve_guild(slug: str, config: ServerConfig, bridge: BridgeClient) -> int:
    slug_map = await _build_guild_slug_map(config, bridge)
    guild_id = resolve_guild_id(slug, slug_map)
    if guild_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')
    return guild_id


# --- global ops (no guild) ---


@router.get('/ops/info/version')
async def ops_info_version(
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    return await bridge.get_op('/bridge/ops/info/version')


@router.get('/ops/info/scheduler')
async def ops_info_scheduler(
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    return await bridge.get_op('/bridge/ops/info/scheduler')


@router.get('/ops/trigger/logo')
async def ops_trigger_logo_get(
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    return await bridge.post_op('/bridge/ops/trigger/logo')


@router.post('/ops/trigger/logo')
async def ops_trigger_logo(
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    return await bridge.post_op('/bridge/ops/trigger/logo')


@router.post('/ops/trigger/emoji-sync')
async def ops_trigger_emoji_sync(
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    return await bridge.post_op('/bridge/ops/trigger/emoji-sync')


@router.get('/ops/inspect/message')
async def ops_inspect_message(
    guild_id: int,
    channel_id: int,
    message_id: int,
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    return await bridge.get_op(
        '/bridge/ops/inspect/message',
        params={'guild_id': guild_id, 'channel_id': channel_id, 'message_id': message_id},
    )


# --- guild-scoped ops ---


@router.post('/ops/{slug}/backfill/channel')
async def ops_backfill_channel(
    slug: str,
    body: BackfillChannelBody,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op('/bridge/ops/backfill/channel', {'guild_id': guild_id, 'channel_id': body.channel_id})


@router.post('/ops/{slug}/backfill/guild')
async def ops_backfill_guild(
    slug: str,
    body: BackfillGuildBody,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op('/bridge/ops/backfill/guild', {'guild_id': guild_id, 'lookback_days': body.lookback_days})


@router.post('/ops/{slug}/ccboard/regen')
async def ops_ccboard_regen(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op('/bridge/ops/ccboard/regen', {'guild_id': guild_id})


@router.post('/ops/{slug}/ccboard/purge')
async def ops_ccboard_purge(
    slug: str,
    body: CcboardPurgeBody,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op('/bridge/ops/ccboard/purge', {'guild_id': guild_id, 'message_id': body.message_id})


@router.post('/ops/{slug}/ccboard/recover')
async def ops_ccboard_recover(
    slug: str,
    body: CcboardDryRunBody,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op(
        '/bridge/ops/ccboard/recover',
        {'guild_id': guild_id, 'dry_run': body.dry_run},
        timeout=_LONG_TIMEOUT,
    )


@router.post('/ops/{slug}/ccboard/cleanup')
async def ops_ccboard_cleanup(
    slug: str,
    body: CcboardDryRunBody,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op(
        '/bridge/ops/ccboard/cleanup',
        {'guild_id': guild_id, 'dry_run': body.dry_run},
        timeout=_LONG_TIMEOUT,
    )


@router.post('/ops/{slug}/ccboard/recount')
async def ops_ccboard_recount(
    slug: str,
    body: CcboardRecountBody,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op(
        '/bridge/ops/ccboard/recount',
        {'guild_id': guild_id, 'message_id': body.message_id, 'dry_run': body.dry_run},
        timeout=_LONG_TIMEOUT,
    )


@router.get('/ops/{slug}/ccboard/reactions')
async def ops_ccboard_reactions(
    slug: str,
    message_id: int,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.get_op(
        '/bridge/ops/ccboard/reactions',
        params={'guild_id': guild_id, 'message_id': message_id},
    )


@router.post('/ops/{slug}/trigger/year-links')
async def ops_trigger_year_links(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.post_op('/bridge/ops/trigger/year-links', {'guild_id': guild_id})


@router.get('/ops/{slug}/info/year-stats')
async def ops_info_year_stats(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.get_op('/bridge/ops/info/year-stats', params={'guild_id': guild_id})


@router.get('/ops/{slug}/info/epoch')
async def ops_info_epoch(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    guild_id = await _resolve_guild(slug, config, bridge)
    return await bridge.get_op('/bridge/ops/info/epoch', params={'guild_id': guild_id})
