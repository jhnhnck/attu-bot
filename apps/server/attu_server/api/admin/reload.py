# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.reload | config reload trigger endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from attu_server.api.admin.guilds import _build_guild_slug_map
from attu_server.api.admin.slugs import resolve_guild_id
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig
from attu_server.deps import get_bridge, get_config


router = APIRouter()


class GuildReloadBody(BaseModel):
    guild_slug: str


@router.post('/reload/guild')
async def reload_guild(
    body: GuildReloadBody,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> dict[str, Any]:
    slug_map = await _build_guild_slug_map(config, bridge)
    guild_id = resolve_guild_id(body.guild_slug, slug_map)
    if guild_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')
    await bridge.trigger_reload('guild', guild_id)
    return {'ok': True}


@router.post('/reload/theme')
async def reload_theme(
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> dict[str, Any]:
    await bridge.trigger_reload('theme')
    return {'ok': True}


@router.post('/reload/system')
async def reload_system(
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> dict[str, Any]:
    await bridge.trigger_reload('system')
    return {'ok': True}
