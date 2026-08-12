# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.fix | fix/maintenance operation endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from attu_server.api.admin.guilds import _build_guild_slug_map
from attu_server.api.admin.slugs import resolve_guild_id
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig
from attu_server.deps import get_bridge, get_config


router = APIRouter()


@router.post('/guilds/{slug}/fix/recalculate-starboard')
async def fix_recalculate_starboard(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> Any:
    slug_map = await _build_guild_slug_map(config, bridge)
    guild_id = resolve_guild_id(slug, slug_map)
    if guild_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')

    r = await bridge.post_fix('recalculate-starboard', guild_id=guild_id)
    if r.status_code == status.HTTP_404_NOT_FOUND:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content={'detail': 'bridge fix endpoint not yet available', 'operation': 'recalculate-starboard'},
        )
    r.raise_for_status()
    return {'ok': True}
